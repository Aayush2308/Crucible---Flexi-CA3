"""Orchestrator unit tests — Phase 3.

Author: Aayush Agarwal (Aayush2308)
Module: tests/test_orchestrator.py

Tests cover:
  - Triage node produces a valid OrchestratorPlan.
  - Dispatch node invokes all three worker agents.
  - Conflict detection identifies overlapping severity disagreements.
  - Peer-critique loop routes CritiqueRequests and collects responses.
  - Arbitration node resolves open conflicts with rulings.
  - Synthesis node produces a non-empty FinalReport with correct metrics.
  - Termination guard fires at MAX_ROUNDS and marks state terminated.
  - Full graph run produces a FinalReport with status 'completed'.
"""

from __future__ import annotations

import os

import pytest

os.environ["CRUCIBLE_MOCK_LLM"] = "1"

from agents.orchestrator import (
    MAX_ROUNDS,
    Orchestrator,
    arbitration_node,
    conflict_detection_node,
    dispatch_workers_node,
    peer_critique_node,
    synthesis_node,
    termination_guard_node,
    triage_node,
)
from lib.blackboard import make_initial_state
from lib.schemas import (
    Conflict,
    CritiqueRequest,
    Finding,
    FindingSet,
    ReviewRequest,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_CODE = "def add(a, b):\n    return a + b\n"

VULN_CODE = """
import subprocess
def run(cmd):
    query = "SELECT * FROM users WHERE id='" + cmd + "'"
    return subprocess.call(cmd)
"""


def _make_state(code: str = SIMPLE_CODE, context: str = "") -> dict:
    req = ReviewRequest(input_code=code, language="python", context=context)
    return make_initial_state(req)


# ---------------------------------------------------------------------------
# Test 1: Triage node produces a valid OrchestratorPlan
# ---------------------------------------------------------------------------

def test_triage_node_produces_plan():
    state = _make_state()
    state = triage_node(state)

    plan = state.get("orchestrator_plan")
    assert plan is not None, "OrchestratorPlan should be written to state"
    assert len(plan.agents) == 3, "Plan should include all three specialist agents"
    assert "logic_reviewer" in plan.agents
    assert "security_auditor" in plan.agents
    assert "style_doc_agent" in plan.agents
    assert plan.next_action == "dispatch_workers"
    assert state.get("current_round", 0) == 1


# ---------------------------------------------------------------------------
# Test 2: Dispatch node runs all three workers and posts findings
# ---------------------------------------------------------------------------

def test_dispatch_workers_invokes_all_agents():
    state = _make_state(code=VULN_CODE)
    state = triage_node(state)
    state = dispatch_workers_node(state)

    assert len(state.get("logic_findings", [])) == 1, "LogicReviewer should post one FindingSet"
    assert len(state.get("security_findings", [])) == 1, "SecurityAuditor should post one FindingSet"
    assert len(state.get("style_findings", [])) == 1, "StyleDocAgent should post one FindingSet"

    total_events = len(state.get("trace_events", []))
    assert total_events > 5, f"Expected >5 trace events after dispatch, got {total_events}"


# ---------------------------------------------------------------------------
# Test 3: Conflict detection — overlapping lines with severity difference ≥ 2
# ---------------------------------------------------------------------------

def test_conflict_detection_finds_overlapping_severity_disagreement():
    state = _make_state()

    # Inject two synthetic FindingSets with overlapping line ranges but different severities
    finding_a = Finding(
        line_start=1, line_end=5,
        category="complexity", severity="info",
        evidence="Low complexity note.", recommendation="No action needed.",
    )
    finding_b = Finding(
        line_start=3, line_end=7,
        category="injection", severity="critical",
        evidence="SQL injection detected.", recommendation="Use parameterized queries.",
        cwe_id="CWE-89",
    )

    state["logic_findings"] = [
        FindingSet(agent="logic_reviewer", round=0, findings=[finding_a])
    ]
    state["security_findings"] = [
        FindingSet(agent="security_auditor", round=0, findings=[finding_b])
    ]
    state["style_findings"] = []

    state = conflict_detection_node(state)

    conflicts = state.get("conflicts", [])
    assert len(conflicts) == 1, f"Expected 1 conflict, got {len(conflicts)}"
    assert conflicts[0].status == "open"
    assert "logic_reviewer" in conflicts[0].agents_involved
    assert "security_auditor" in conflicts[0].agents_involved

    critiques = state.get("critique_requests", [])
    assert len(critiques) == 2, f"Expected 2 critique requests (one per agent), got {len(critiques)}"


# ---------------------------------------------------------------------------
# Test 4: No conflict when line ranges do NOT overlap
# ---------------------------------------------------------------------------

def test_conflict_detection_no_overlap():
    state = _make_state()

    finding_a = Finding(
        line_start=1, line_end=3, category="complexity", severity="info",
        evidence="Low.", recommendation="None.",
    )
    finding_b = Finding(
        line_start=10, line_end=15, category="injection", severity="critical",
        evidence="Injection.", recommendation="Fix.",
    )

    state["logic_findings"] = [FindingSet(agent="logic_reviewer", round=0, findings=[finding_a])]
    state["security_findings"] = [FindingSet(agent="security_auditor", round=0, findings=[finding_b])]
    state["style_findings"] = []

    state = conflict_detection_node(state)
    assert len(state.get("conflicts", [])) == 0


# ---------------------------------------------------------------------------
# Test 5: Peer-critique loop processes CritiqueRequests
# ---------------------------------------------------------------------------

def test_peer_critique_collects_responses():
    state = _make_state()

    finding = Finding(
        line_start=1, line_end=5, category="injection", severity="critical",
        evidence="SQL injection detected.", recommendation="Use parameterized queries.",
    )
    state["security_findings"] = [FindingSet(agent="security_auditor", round=0, findings=[finding])]
    state["logic_findings"] = []
    state["style_findings"] = []

    critique = CritiqueRequest(
        to_agent="security_auditor",
        round=1,
        challenged_finding_id=finding.finding_id,
        challenge_reason="This looks like a logic concern, not a security one.",
        supporting_evidence="No user input is present in this function.",
    )
    state["critique_requests"] = [critique]

    state = peer_critique_node(state)

    responses = state.get("critique_responses", [])
    assert len(responses) >= 1, "Peer critique should yield at least one response"
    assert responses[0].critique_id == critique.critique_id
    assert responses[0].decision in ("accept", "revise", "reject")
    # Critique requests should be cleared after processing
    assert state.get("critique_requests", []) == []


# ---------------------------------------------------------------------------
# Test 6: Arbitration node resolves open conflicts with rulings
# ---------------------------------------------------------------------------

def test_arbitration_resolves_open_conflicts():
    state = _make_state()

    finding_a = Finding(
        line_start=1, line_end=5, category="complexity", severity="info",
        evidence="Low.", recommendation="None.", finding_id="fid_a",
    )
    finding_b = Finding(
        line_start=3, line_end=7, category="injection", severity="critical",
        evidence="SQL injection.", recommendation="Fix.", cwe_id="CWE-89", finding_id="fid_b",
    )
    conflict = Conflict(
        agents_involved=["logic_reviewer", "security_auditor"],
        finding_ids=["fid_a", "fid_b"],
        line_range=[3, 5],
        description="Severity disagreement on overlapping code region.",
        status="open",
    )

    state["logic_findings"] = [FindingSet(agent="logic_reviewer", round=0, findings=[finding_a])]
    state["security_findings"] = [FindingSet(agent="security_auditor", round=0, findings=[finding_b])]
    state["style_findings"] = []
    state["conflicts"] = [conflict]

    state = arbitration_node(state)

    rulings = state.get("arbitration_rulings", [])
    assert len(rulings) == 1, "Should produce exactly one arbitration ruling"
    assert rulings[0].conflict_id == conflict.conflict_id
    assert rulings[0].ruling in (
        "security_correct",
        "logic_correct",
        "style_correct",
        "both_valid_different_aspects",
        "disputed_insufficient_evidence",
    )


# ---------------------------------------------------------------------------
# Test 7: Synthesis node produces a complete FinalReport
# ---------------------------------------------------------------------------

def test_synthesis_produces_final_report():
    state = _make_state(code=VULN_CODE)
    state = triage_node(state)
    state = dispatch_workers_node(state)
    state = synthesis_node(state)

    report = state.get("final_report")
    assert report is not None, "FinalReport should be present in state"
    assert report.status in ("completed", "terminated_max_rounds")
    assert report.overall_severity in ("critical", "high", "medium", "low", "info")
    assert len(report.executive_summary) > 10
    assert report.metrics.get("total_rounds", 0) > 0
    assert report.metrics.get("trace_events", 0) > 0


# ---------------------------------------------------------------------------
# Test 8: Termination guard triggers at MAX_ROUNDS
# ---------------------------------------------------------------------------

def test_termination_guard_triggers_at_max_rounds():
    state = _make_state()
    state["current_round"] = MAX_ROUNDS  # Simulate exhausted rounds

    state = termination_guard_node(state)

    assert state.get("terminated") is True
    assert "Maximum" in state.get("termination_reason", "")
    events = state.get("trace_events", [])
    guard_events = [e for e in events if e.message_type == "termination_guard"]
    assert len(guard_events) == 1


# ---------------------------------------------------------------------------
# Test 9: Full graph run completes with status 'completed'
# ---------------------------------------------------------------------------

def test_full_orchestrator_graph_run():
    req = ReviewRequest(
        input_code=VULN_CODE,
        language="python",
        context="Full orchestrator integration test",
    )
    state = make_initial_state(req)

    orch = Orchestrator()
    final_state = orch.run(state)

    report = final_state.get("final_report")
    assert report is not None, "FinalReport must be produced by full graph"
    assert report.status in ("completed", "terminated_max_rounds")
    assert len(final_state.get("trace_events", [])) > 5
    assert len(final_state.get("logic_findings", [])) >= 1
    assert len(final_state.get("security_findings", [])) >= 1
    assert len(final_state.get("style_findings", [])) >= 1
