"""Crucible Logic Reviewer Agent.

Author: Anum Agarwal (anum777)
Role: Logic Reviewer Specialist
Module: agents/logic_reviewer.py
"""

from __future__ import annotations

import json
from typing import Any

from agents.base import BaseAgent
from lib.blackboard import CrucibleState
from lib.llm_provider import call_llm
from lib.schemas import (
    AgentName,
    CritiqueRequest,
    CritiqueResponse,
    Finding,
    FindingSet,
    ToolCallLog,
)
from lib.trace_logger import record_event
from tools.logic_tools import analyze_ast, compute_complexity
from tools.tool_base import run_tool


class LogicReviewer(BaseAgent):
    """Specialist agent focusing exclusively on algorithmic soundness and logic flaws."""

    def __init__(self, agent_name: AgentName = "logic_reviewer", model_name: str = "gemini-2.5-flash") -> None:
        super().__init__(agent_name=agent_name, model_name=model_name)

    def run(self, state: CrucibleState) -> CrucibleState:
        """Execute logic inspection: static tools first, then LLM structured review."""
        code = state["input_code"]
        language = state["input_language"]
        fault_injection = state.get("fault_injection", "")
        plan = state.get("orchestrator_plan")
        focus = plan.focus_areas.get(self.agent_name, []) if plan else []

        tool_logs: list[ToolCallLog] = []

        # 1. AST Analysis Tool
        ast_result, state = run_tool(
            tool_fn=analyze_ast,
            code=code,
            tool_name="ast_analyzer",
            fault_injection=fault_injection,
            state=state,
            event_from=self.agent_name,
        )
        tool_logs.append(
            ToolCallLog(
                tool_name="ast_analyzer",
                success=ast_result.success,
                error=ast_result.error,
                output_summary=f"Functions: {len(ast_result.output.get('functions', []))}" if ast_result.output else "failed",
                duration_ms=ast_result.duration_ms,
                fallback_used=ast_result.fallback_used,
            )
        )

        # 2. Complexity Tool
        cc_result, state = run_tool(
            tool_fn=compute_complexity,
            code=code,
            tool_name="complexity_scorer",
            fault_injection=fault_injection,
            state=state,
            event_from=self.agent_name,
        )
        tool_logs.append(
            ToolCallLog(
                tool_name="complexity_scorer",
                success=cc_result.success,
                error=cc_result.error,
                output_summary=f"Blocks analyzed: {len(cc_result.output.get('blocks', []))}" if cc_result.output else "failed",
                duration_ms=cc_result.duration_ms,
                fallback_used=cc_result.fallback_used,
            )
        )

        # 3. LLM Reasoning
        system_prompt = (
            "You are the Logic Reviewer for Crucible, an autonomous multi-agent code evaluation system.\n"
            "Your ONLY responsibility is to detect logical correctness issues, algorithmic bugs, off-by-one errors,\n"
            "unhandled edge cases, dead code, and excessive complexity.\n"
            "Do NOT report security vulnerabilities (e.g. SQL injection) or style/formatting violations.\n"
            "Output strictly valid JSON conforming to the FindingSet schema."
        )

        user_prompt = (
            f"Language: {language}\n"
            f"Context: {state.get('input_context', 'General code inspection')}\n"
            f"Target focus areas: {focus}\n\n"
            f"Static Tool Summaries:\n"
            f"- AST Tool Result: {json.dumps(ast_result.output if ast_result.success else {'error': ast_result.error})}\n"
            f"- Cyclomatic Complexity: {json.dumps(cc_result.output if cc_result.success else {'error': cc_result.error})}\n\n"
            f"Source Code:\n{code}"
        )

        finding_set, state = call_llm(
            model_name=self.model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=FindingSet,
            state=state,
            event_from=self.agent_name,
        )

        # Ensure agent metadata and tool logs are preserved
        finding_set.agent = self.agent_name
        finding_set.round = state.get("current_round", 0)
        finding_set.tool_results_summary = tool_logs

        # Append findings to blackboard
        logic_findings = state.get("logic_findings", [])
        logic_findings.append(finding_set)
        state["logic_findings"] = logic_findings

        record_event(
            state=state,
            from_agent=self.agent_name,
            to_agent="blackboard",
            message_type="finding",
            summary=f"Logic Reviewer reported {len(finding_set.findings)} findings (confidence: {finding_set.overall_confidence:.2f}).",
            payload=finding_set.model_dump(),
        )

        return state

    def handle_critique(self, state: CrucibleState) -> CrucibleState:
        """Handle challenge requests from the Orchestrator regarding contested findings."""
        requests = self.get_my_critique_requests(state)
        if not requests:
            return state

        responses = state.get("critique_responses", [])

        for req in requests:
            # Locate challenged finding
            all_my_findings = [f for fset in state.get("logic_findings", []) for f in fset.findings]
            matched = next((f for f in all_my_findings if f.finding_id == req.challenged_finding_id), None)

            # Re-evaluate based on challenge reason
            if matched and "security" in req.challenge_reason.lower():
                # Yield to security when boundary/sanitization overlap occurs
                decision = "accept"
                rationale = (
                    f"Accepted challenge on finding {req.challenged_finding_id}: "
                    "The issue primarily constitutes an injection vulnerability rather than pure algorithmic failure."
                )
                updated = None
            elif matched:
                decision = "revise"
                updated = matched.model_copy()
                updated.severity = "medium"
                updated.evidence = f"{matched.evidence} [Revised following critique: {req.challenge_reason}]"
                rationale = f"Revised finding {req.challenged_finding_id} severity to medium based on provided critique."
            else:
                decision = "reject"
                rationale = f"Finding {req.challenged_finding_id} was not found or remains valid as reported."
                updated = None

            resp = CritiqueResponse(
                critique_id=req.critique_id,
                from_agent=self.agent_name,
                decision=decision,
                rationale=rationale,
                updated_finding=updated,
            )
            responses.append(resp)

            record_event(
                state=state,
                from_agent=self.agent_name,
                to_agent="orchestrator",
                message_type="critique_response",
                summary=f"Logic Reviewer responded to critique: {decision}",
                payload=resp.model_dump(),
                decision_rationale=rationale,
            )

        state["critique_responses"] = responses
        return state
