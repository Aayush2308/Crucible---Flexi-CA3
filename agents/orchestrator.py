"""Crucible Orchestrator Agent & LangGraph Coordination Graph.

Primary Owner: Aayush Agarwal (Aayush2308)
Module: agents/orchestrator.py

Constructs the full multi-agent StateGraph that:
  1. Triage Node        — LLM generates OrchestratorPlan.
  2. Worker Fan-Out     — Dispatches LogicReviewer, SecurityAuditor, StyleDocAgent in parallel.
  3. Conflict Detection — Scans blackboard for overlapping line ranges with severity disagreements.
  4. Peer-Critique Loop — Issues CritiqueRequests to conflicting agents; collects responses.
  5. Arbitration Node   — Resolves deadlocked conflicts with written LLM rationale.
  6. Synthesis Node     — Compiles the final unified ReviewReport.
  7. Termination Guard  — Enforces max_rounds = 3 to prevent infinite loops.
"""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.graph import END, StateGraph

from agents.base import BaseAgent
from agents.logic_reviewer import LogicReviewer
from agents.security_auditor import SecurityAuditor
from agents.style_doc_agent import StyleDocAgent
from lib.blackboard import CrucibleState
from lib.llm_provider import LLMFailure, call_llm
from lib.schemas import (
    AgentName,
    ArbitrationRuling,
    Conflict,
    CritiqueRequest,
    FinalReport,
    Finding,
    FindingSet,
    OrchestratorPlan,
    OrchestratorReviewDecision,
    SeverityLevel,
)
from lib.trace_logger import record_event

# ---------------------------------------------------------------------------
# Severity ranking helpers
# ---------------------------------------------------------------------------

_SEVERITY_RANK: dict[SeverityLevel, int] = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}

MAX_ROUNDS = 3
_OVERLAP_THRESHOLD = 0  # lines must share at least 1 line to be "overlapping"


def _severity_rank(s: SeverityLevel | str) -> int:
    return _SEVERITY_RANK.get(str(s).lower(), 0)  # type: ignore[arg-type]


def _highest_severity(findings: list[Finding]) -> SeverityLevel:
    """Return the highest severity level among a list of findings."""
    if not findings:
        return "info"
    return max(findings, key=lambda f: _severity_rank(f.severity)).severity


def _ranges_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """Return True if two inclusive line ranges share at least one line."""
    return a_start <= b_end and b_start <= a_end


# ---------------------------------------------------------------------------
# Node 1: Triage — LLM generates OrchestratorPlan
# ---------------------------------------------------------------------------

def triage_node(state: CrucibleState) -> CrucibleState:
    """Analyse incoming code and produce a triage plan for the worker agents."""
    code = state["input_code"]
    language = state.get("input_language", "python")
    context = state.get("input_context", "")
    current_round = state.get("current_round", 0)

    system_prompt = (
        "You are the Orchestrator of Crucible, an autonomous multi-agent code review system.\n"
        "Given a code snippet, produce a structured OrchestratorPlan JSON.\n"
        "Your plan must:\n"
        "  - List all three agents: logic_reviewer, security_auditor, style_doc_agent.\n"
        "  - Set execution_order to 'parallel'.\n"
        "  - Assign focus_areas for each agent based on evident code characteristics.\n"
        "  - Set budget to 3 (maximum review rounds).\n"
        "  - Set next_action to 'dispatch_workers'.\n"
        "Output ONLY valid JSON conforming to OrchestratorPlan schema."
    )
    user_prompt = (
        f"Language: {language}\n"
        f"Context: {context or 'General multi-agent code review'}\n"
        f"Review Round: {current_round}\n\n"
        f"Source Code:\n{code}"
    )

    try:
        plan, state = call_llm(
            model_name="gemini-2.5-flash",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=OrchestratorPlan,
            state=state,
            event_from="orchestrator",
        )
    except LLMFailure:
        # Fallback: default plan with all three agents
        plan = OrchestratorPlan(
            agents=["logic_reviewer", "security_auditor", "style_doc_agent"],
            execution_order="parallel",
            focus_areas={},
            budget=MAX_ROUNDS,
            rationale="Fallback plan: LLM triage unavailable; dispatching all agents.",
            next_action="dispatch_workers",
        )

    state["orchestrator_plan"] = plan
    state["current_round"] = current_round + 1

    record_event(
        state=state,
        from_agent="orchestrator",
        to_agent="blackboard",
        message_type="plan",
        summary=(
            f"Triage complete (round {state['current_round']}): "
            f"dispatching {len(plan.agents)} agents — {', '.join(plan.agents)}."
        ),
        payload=plan.model_dump(),
        decision_rationale=plan.rationale,
    )

    return state


# ---------------------------------------------------------------------------
# Node 2: Worker Fan-Out — run all three specialist agents
# ---------------------------------------------------------------------------

def dispatch_workers_node(state: CrucibleState) -> CrucibleState:
    """Invoke each specialist agent sequentially (logic, security, style)."""
    agents: list[BaseAgent] = [
        LogicReviewer(),
        SecurityAuditor(),
        StyleDocAgent(),
    ]

    record_event(
        state=state,
        from_agent="orchestrator",
        to_agent="blackboard",
        message_type="plan",
        summary=f"Dispatching {len(agents)} specialist worker agents.",
        payload={"agents": [a.agent_name for a in agents]},
    )

    for agent in agents:
        try:
            state = agent.run(state)
        except Exception as exc:
            record_event(
                state=state,
                from_agent="orchestrator",
                to_agent="blackboard",
                message_type="error",
                summary=f"Worker agent {agent.agent_name} raised an exception: {exc}",
                payload={"agent": agent.agent_name, "error": str(exc)},
            )

    return state


# ---------------------------------------------------------------------------
# Node 3: Conflict Detection — scan blackboard for overlapping disagreements
# ---------------------------------------------------------------------------

def conflict_detection_node(state: CrucibleState) -> CrucibleState:
    """Detect overlapping line-range findings with diverging severity levels."""
    all_finding_sets: list[FindingSet] = (
        state.get("logic_findings", [])
        + state.get("security_findings", [])
        + state.get("style_findings", [])
    )

    # Flatten all individual findings with their owning agent name
    tagged: list[tuple[AgentName, Finding]] = []
    for fset in all_finding_sets:
        for f in fset.findings:
            tagged.append((fset.agent, f))

    conflicts: list[Conflict] = list(state.get("conflicts", []))
    critique_requests: list[CritiqueRequest] = list(state.get("critique_requests", []))
    current_round = state.get("current_round", 0)

    # Pairwise comparison
    for i in range(len(tagged)):
        for j in range(i + 1, len(tagged)):
            agent_a, finding_a = tagged[i]
            agent_b, finding_b = tagged[j]

            # Skip same-agent comparisons
            if agent_a == agent_b:
                continue

            # Check for line-range overlap
            if not _ranges_overlap(
                finding_a.line_start, finding_a.line_end,
                finding_b.line_start, finding_b.line_end,
            ):
                continue

            # Check for severity disagreement (≥2 levels apart = conflict)
            rank_diff = abs(_severity_rank(finding_a.severity) - _severity_rank(finding_b.severity))
            if rank_diff < 2:
                continue

            conflict = Conflict(
                agents_involved=[agent_a, agent_b],
                finding_ids=[finding_a.finding_id, finding_b.finding_id],
                line_range=[
                    max(finding_a.line_start, finding_b.line_start),
                    min(finding_a.line_end, finding_b.line_end),
                ],
                description=(
                    f"{agent_a} rated lines {finding_a.line_start}-{finding_a.line_end} "
                    f"as {finding_a.severity} ({finding_a.category}), but "
                    f"{agent_b} rated lines {finding_b.line_start}-{finding_b.line_end} "
                    f"as {finding_b.severity} ({finding_b.category})."
                ),
                status="open",
            )
            conflicts.append(conflict)

            record_event(
                state=state,
                from_agent="orchestrator",
                to_agent="blackboard",
                message_type="finding",
                summary=f"Conflict detected between {agent_a} and {agent_b} on lines {conflict.line_range}.",
                payload=conflict.model_dump(),
            )

            # Issue CritiqueRequests to both agents involved in the conflict
            for (challenger_agent, target_agent, challenged_finding) in [
                (agent_b, agent_a, finding_a),
                (agent_a, agent_b, finding_b),
            ]:
                critique_req = CritiqueRequest(
                    to_agent=target_agent,
                    round=current_round,
                    challenged_finding_id=challenged_finding.finding_id,
                    challenge_reason=(
                        f"{challenger_agent} disagrees: their finding on the same code region "
                        f"has severity '{finding_b.severity if target_agent == agent_a else finding_a.severity}'. "
                        f"Please reconsider your '{challenged_finding.severity}' classification."
                    ),
                    supporting_evidence=(
                        f"Conflicting finding: {finding_b.evidence if target_agent == agent_a else finding_a.evidence}"
                    ),
                )
                critique_requests.append(critique_req)

    state["conflicts"] = conflicts
    state["critique_requests"] = critique_requests

    conflict_count = len([c for c in conflicts if c.status == "open"])
    record_event(
        state=state,
        from_agent="orchestrator",
        to_agent="blackboard",
        message_type="plan",
        summary=f"Conflict detection complete: {conflict_count} open conflict(s) found.",
        payload={"open_conflicts": conflict_count, "total_conflicts": len(conflicts)},
    )

    return state


# ---------------------------------------------------------------------------
# Node 4: Peer-Critique Loop — agents respond to CritiqueRequests
# ---------------------------------------------------------------------------

def peer_critique_node(state: CrucibleState) -> CrucibleState:
    """Route outstanding CritiqueRequests to each target agent's handle_critique()."""
    pending = state.get("critique_requests", [])
    if not pending:
        return state

    agents_map: dict[AgentName, BaseAgent] = {
        "logic_reviewer": LogicReviewer(),
        "security_auditor": SecurityAuditor(),
        "style_doc_agent": StyleDocAgent(),
    }

    record_event(
        state=state,
        from_agent="orchestrator",
        to_agent="blackboard",
        message_type="critique_request",
        summary=f"Issuing {len(pending)} critique request(s) to worker agents.",
        payload={"count": len(pending)},
    )

    for agent_name, agent in agents_map.items():
        targeted = [r for r in pending if r.to_agent == agent_name]
        if targeted:
            try:
                state = agent.handle_critique(state)
            except Exception as exc:
                record_event(
                    state=state,
                    from_agent="orchestrator",
                    to_agent="blackboard",
                    message_type="error",
                    summary=f"Critique handler for {agent_name} raised: {exc}",
                    payload={"agent": agent_name, "error": str(exc)},
                )

    # Clear processed requests so they don't repeat
    state["critique_requests"] = []

    return state


# ---------------------------------------------------------------------------
# Node 5: Review Decision — LLM decides next_action after seeing responses
# ---------------------------------------------------------------------------

def review_decision_node(state: CrucibleState) -> CrucibleState:
    """Orchestrator evaluates critique responses and decides: converge or arbitrate."""
    responses = state.get("critique_responses", [])
    conflicts = state.get("conflicts", [])
    open_conflicts = [c for c in conflicts if c.status == "open"]
    current_round = state.get("current_round", 0)

    # Collect response summary for LLM context
    response_summaries = [
        f"- {r.from_agent}: {r.decision} on finding {r.critique_id}: {r.rationale[:120]}"
        for r in responses
    ]

    system_prompt = (
        "You are the Orchestrator reviewing critique responses from specialist agents.\n"
        "Evaluate the responses and decide the next action:\n"
        "  - 'converge'  : All conflicts resolved or no open conflicts remain.\n"
        "  - 'arbitrate' : One or more conflicts still unresolved — require arbitration.\n"
        "  - 'revise'    : A finding needs significant revision before final report.\n"
        "  - 'replan'    : Unexpected state requiring a complete restart of the analysis.\n"
        "Output ONLY valid JSON conforming to OrchestratorReviewDecision schema."
    )
    user_prompt = (
        f"Open conflicts remaining: {len(open_conflicts)}\n"
        f"Critique responses received:\n" + "\n".join(response_summaries or ["(none)"]) + "\n\n"
        f"Review round: {current_round} / {MAX_ROUNDS}"
    )

    try:
        decision, state = call_llm(
            model_name="gemini-2.5-flash",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=OrchestratorReviewDecision,
            state=state,
            event_from="orchestrator",
        )
    except LLMFailure:
        # Fallback: if critiques were accepted → converge, else arbitrate
        rejected_count = sum(1 for r in responses if r.decision == "reject")
        next_action = "arbitrate" if (rejected_count > 0 and open_conflicts) else "converge"
        decision = OrchestratorReviewDecision(
            next_action=next_action,
            conflicts_detected=open_conflicts,
            revision_targets=[],
            replan_reason=None,
            rationale="Fallback decision: LLM review decision unavailable.",
        )

    record_event(
        state=state,
        from_agent="orchestrator",
        to_agent="blackboard",
        message_type="review",
        summary=f"Review decision: next_action='{decision.next_action}'. Rationale: {decision.rationale[:100]}",
        payload=decision.model_dump(),
        decision_rationale=decision.rationale,
    )

    # Store decision on the plan for routing
    current_plan = state.get("orchestrator_plan")
    if current_plan:
        current_plan.next_action = (
            "converge" if decision.next_action in ("converge", "revise")
            else "dispatch_workers"  # triggers arbitration branch via conditional edge
        )
        state["orchestrator_plan"] = current_plan

    # Carry decision signal on state for routing function
    state["_review_decision"] = decision.next_action  # type: ignore[typeddict-unknown-key]

    return state


# ---------------------------------------------------------------------------
# Node 6: Arbitration — LLM resolves each remaining open conflict
# ---------------------------------------------------------------------------

def arbitration_node(state: CrucibleState) -> CrucibleState:
    """Render binding rulings for each unresolved conflict using LLM arbitration."""
    open_conflicts = [c for c in state.get("conflicts", []) if c.status == "open"]
    rulings: list[ArbitrationRuling] = list(state.get("arbitration_rulings", []))

    if not open_conflicts:
        return state

    all_findings_map: dict[str, Finding] = {}
    for fset in (
        state.get("logic_findings", [])
        + state.get("security_findings", [])
        + state.get("style_findings", [])
    ):
        for f in fset.findings:
            all_findings_map[f.finding_id] = f

    for conflict in open_conflicts:
        conflicting_findings = [
            all_findings_map[fid]
            for fid in conflict.finding_ids
            if fid in all_findings_map
        ]
        finding_descriptions = "\n".join(
            f"  - [{f.severity.upper()}] {f.category} by agent (line {f.line_start}-{f.line_end}): {f.evidence}"
            for f in conflicting_findings
        )

        system_prompt = (
            "You are the impartial Arbitrator of Crucible.\n"
            "Two specialist agents disagree about the severity of an issue in the same code region.\n"
            "Render a binding ruling using one of these values for 'ruling':\n"
            "  security_correct | logic_correct | style_correct | both_valid_different_aspects | disputed_insufficient_evidence\n"
            "Choose the ruling that best aligns with risk-based reasoning.\n"
            "If security is involved, it typically takes precedence.\n"
            "Output ONLY valid JSON conforming to ArbitrationRuling schema."
        )
        user_prompt = (
            f"Conflict ID: {conflict.conflict_id}\n"
            f"Agents involved: {', '.join(conflict.agents_involved)}\n"
            f"Description: {conflict.description}\n\n"
            f"Conflicting Findings:\n{finding_descriptions}\n\n"
            "Critique responses already attempted but did not resolve the disagreement."
        )

        try:
            ruling, state = call_llm(
                model_name="gemini-2.5-flash",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=ArbitrationRuling,
                state=state,
                event_from="orchestrator",
            )
            # Bind conflict_id to match this conflict
            ruling = ArbitrationRuling(
                conflict_id=conflict.conflict_id,
                ruling=ruling.ruling,
                rationale=ruling.rationale,
                severity_override=ruling.severity_override,
                final_recommendation=ruling.final_recommendation,
            )
        except LLMFailure:
            ruling = ArbitrationRuling(
                conflict_id=conflict.conflict_id,
                ruling="disputed_insufficient_evidence",
                rationale="Arbitration LLM unavailable; conflict marked as disputed.",
                severity_override=None,
                final_recommendation="Manual review recommended for this conflict.",
            )

        rulings.append(ruling)
        conflict.status = "arbitrated"

        record_event(
            state=state,
            from_agent="orchestrator",
            to_agent="blackboard",
            message_type="arbitration",
            summary=f"Arbitration ruling for {conflict.conflict_id}: '{ruling.ruling}'. {ruling.rationale[:100]}",
            payload=ruling.model_dump(),
            decision_rationale=ruling.rationale,
        )

    state["arbitration_rulings"] = rulings
    # Update conflicts with arbitrated status
    state["conflicts"] = state.get("conflicts", [])

    return state


# ---------------------------------------------------------------------------
# Node 7: Synthesis — compile FinalReport from all findings & rulings
# ---------------------------------------------------------------------------

def synthesis_node(state: CrucibleState) -> CrucibleState:
    """Compile the unified FinalReport from all findings, responses, and arbitration rulings."""
    run_id = state.get("run_id", f"run_{uuid.uuid4().hex[:8]}")

    # Collect all findings (prioritising revised findings from critique responses)
    revised_findings: dict[str, Finding] = {}
    for resp in state.get("critique_responses", []):
        if resp.updated_finding:
            revised_findings[resp.updated_finding.finding_id] = resp.updated_finding

    all_findings: list[Finding] = []
    for fset in (
        state.get("logic_findings", [])
        + state.get("security_findings", [])
        + state.get("style_findings", [])
    ):
        for f in fset.findings:
            # Use revised version if available, else original
            all_findings.append(revised_findings.get(f.finding_id, f))

    # Apply arbitration severity overrides
    ruling_map: dict[str, ArbitrationRuling] = {}
    for ruling in state.get("arbitration_rulings", []):
        conflict = next(
            (c for c in state.get("conflicts", []) if c.conflict_id == ruling.conflict_id),
            None,
        )
        if conflict and ruling.severity_override:
            for fid in conflict.finding_ids:
                ruling_map[fid] = ruling

    final_findings: list[Finding] = []
    for f in all_findings:
        if f.finding_id in ruling_map:
            overridden = f.model_copy()
            overridden.severity = ruling_map[f.finding_id].severity_override  # type: ignore[assignment]
            overridden.evidence = (
                f.evidence
                + f" [Arbitrated: {ruling_map[f.finding_id].rationale[:80]}]"
            )
            final_findings.append(overridden)
        else:
            final_findings.append(f)

    # Sort by severity (highest first)
    final_findings.sort(key=lambda f: _severity_rank(f.severity), reverse=True)

    overall_severity = _highest_severity(final_findings) if final_findings else "info"
    total_rounds = state.get("current_round", 1)
    status = (
        "terminated_max_rounds" if state.get("terminated") else "completed"
    )

    # Build executive summary
    critical_count = sum(1 for f in final_findings if f.severity == "critical")
    high_count = sum(1 for f in final_findings if f.severity == "high")
    medium_count = sum(1 for f in final_findings if f.severity == "medium")
    executive_summary = (
        f"Crucible multi-agent code review completed in {total_rounds} round(s). "
        f"Total findings: {len(final_findings)} "
        f"(Critical: {critical_count}, High: {high_count}, Medium: {medium_count}). "
        f"Overall severity: {overall_severity.upper()}. "
        f"Arbitration rulings issued: {len(state.get('arbitration_rulings', []))}."
    )

    report = FinalReport(
        run_id=run_id,
        status=status,
        overall_severity=overall_severity,
        executive_summary=executive_summary,
        all_issues=final_findings,
        resolved_conflicts=state.get("arbitration_rulings", []),
        metrics={
            "total_rounds": total_rounds,
            "total_findings": len(final_findings),
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count,
            "low": sum(1 for f in final_findings if f.severity == "low"),
            "info": sum(1 for f in final_findings if f.severity == "info"),
            "conflicts_detected": len(state.get("conflicts", [])),
            "conflicts_arbitrated": len(state.get("arbitration_rulings", [])),
            "trace_events": len(state.get("trace_events", [])),
        },
    )

    state["final_report"] = report

    record_event(
        state=state,
        from_agent="orchestrator",
        to_agent="user",
        message_type="final_report",
        summary=f"Final report synthesized: {len(final_findings)} issues, severity={overall_severity}.",
        payload=report.model_dump(),
        decision_rationale=executive_summary,
    )

    return state


# ---------------------------------------------------------------------------
# Termination Guard — enforces max_rounds ceiling
# ---------------------------------------------------------------------------

def termination_guard_node(state: CrucibleState) -> CrucibleState:
    """Check if max review rounds exceeded; mark state terminated if so."""
    current_round = state.get("current_round", 0)
    if current_round >= MAX_ROUNDS:
        state["terminated"] = True
        state["termination_reason"] = (
            f"Maximum review rounds ({MAX_ROUNDS}) reached. Proceeding directly to synthesis."
        )
        record_event(
            state=state,
            from_agent="orchestrator",
            to_agent="blackboard",
            message_type="termination_guard",
            summary=f"Termination guard triggered at round {current_round}/{MAX_ROUNDS}.",
            payload={"current_round": current_round, "max_rounds": MAX_ROUNDS},
        )
    return state


# ---------------------------------------------------------------------------
# LangGraph Conditional Edge Functions
# ---------------------------------------------------------------------------

def _route_after_triage(state: CrucibleState) -> str:
    """Route: always dispatch workers after triage."""
    return "dispatch_workers"


def _route_after_workers(state: CrucibleState) -> str:
    """Route: after workers, check termination guard then detect conflicts."""
    if state.get("terminated"):
        return "synthesis"
    return "conflict_detection"


def _route_after_conflict_detection(state: CrucibleState) -> str:
    """Route: if conflicts exist go to peer-critique, else go directly to synthesis."""
    open_conflicts = [c for c in state.get("conflicts", []) if c.status == "open"]
    if open_conflicts:
        return "peer_critique"
    return "synthesis"


def _route_after_review_decision(state: CrucibleState) -> str:
    """Route after review decision: converge to synthesis or arbitrate."""
    decision = state.get("_review_decision", "converge")  # type: ignore[typeddict-item]
    if decision == "arbitrate":
        return "arbitration"
    return "synthesis"


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

def build_orchestrator_graph() -> Any:
    """Construct and compile the LangGraph StateGraph for Crucible."""
    graph = StateGraph(CrucibleState)

    # Register nodes
    graph.add_node("triage", triage_node)
    graph.add_node("dispatch_workers", dispatch_workers_node)
    graph.add_node("termination_guard", termination_guard_node)
    graph.add_node("conflict_detection", conflict_detection_node)
    graph.add_node("peer_critique", peer_critique_node)
    graph.add_node("review_decision", review_decision_node)
    graph.add_node("arbitration", arbitration_node)
    graph.add_node("synthesis", synthesis_node)

    # Entry point
    graph.set_entry_point("triage")

    # Edges
    graph.add_edge("triage", "dispatch_workers")
    graph.add_edge("dispatch_workers", "termination_guard")

    graph.add_conditional_edges(
        "termination_guard",
        _route_after_workers,
        {
            "conflict_detection": "conflict_detection",
            "synthesis": "synthesis",
        },
    )

    graph.add_conditional_edges(
        "conflict_detection",
        _route_after_conflict_detection,
        {
            "peer_critique": "peer_critique",
            "synthesis": "synthesis",
        },
    )

    graph.add_edge("peer_critique", "review_decision")

    graph.add_conditional_edges(
        "review_decision",
        _route_after_review_decision,
        {
            "arbitration": "arbitration",
            "synthesis": "synthesis",
        },
    )

    graph.add_edge("arbitration", "synthesis")
    graph.add_edge("synthesis", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public convenience class (mirrors BaseAgent interface)
# ---------------------------------------------------------------------------

class Orchestrator:
    """Top-level entry point wrapping the compiled LangGraph graph."""

    def __init__(self) -> None:
        self._graph = build_orchestrator_graph()

    def run(self, state: CrucibleState) -> CrucibleState:
        """Execute the full multi-agent review graph and return the final state."""
        result = self._graph.invoke(state)
        return result  # type: ignore[return-value]
