"""Crucible Shared Blackboard (LangGraph State).

Defines the CrucibleState TypedDict representing the shared memory
read and written by all agents and system nodes in the LangGraph graph.
"""

from __future__ import annotations

import uuid
from typing import TypedDict
from lib.schemas import (
    ArbitrationRuling,
    Conflict,
    CritiqueRequest,
    CritiqueResponse,
    FinalReport,
    FindingSet,
    OrchestratorPlan,
    ReviewRequest,
    TraceEvent,
)


class CrucibleState(TypedDict, total=False):
    """Shared state container passed between LangGraph nodes."""

    # Run Identifiers & Inputs
    run_id: str
    input_code: str
    input_language: str
    input_context: str
    fault_injection: str

    # Orchestrator Planning & Control
    orchestrator_plan: OrchestratorPlan
    current_round: int
    seq_counter: int

    # Specialist Worker Findings
    logic_findings: list[FindingSet]
    security_findings: list[FindingSet]
    style_findings: list[FindingSet]

    # Inter-Agent Coordination & Arbitration
    conflicts: list[Conflict]
    critique_requests: list[CritiqueRequest]
    critique_responses: list[CritiqueResponse]
    arbitration_rulings: list[ArbitrationRuling]

    # Final Output & Audit Log
    final_report: FinalReport | None
    trace_events: list[TraceEvent]

    # Lifecycle & Termination
    terminated: bool
    termination_reason: str


def make_initial_state(
    request: ReviewRequest,
    fault: str = "",
) -> CrucibleState:
    """Instantiate a pristine CrucibleState from an incoming ReviewRequest."""
    run_id = request.run_id or f"run_{uuid.uuid4().hex[:8]}"
    fault_flag = fault or request.fault_injection or ""

    initial_plan = OrchestratorPlan(
        agents=["logic_reviewer", "security_auditor", "style_doc_agent"],
        execution_order="parallel",
        focus_areas={},
        budget=3,
        rationale="Initial default triage plan.",
        next_action="dispatch_workers",
    )

    return CrucibleState(
        run_id=run_id,
        input_code=request.input_code,
        input_language=request.language or "python",
        input_context=request.context or "",
        fault_injection=fault_flag,
        orchestrator_plan=initial_plan,
        current_round=0,
        seq_counter=0,
        logic_findings=[],
        security_findings=[],
        style_findings=[],
        conflicts=[],
        critique_requests=[],
        critique_responses=[],
        arbitration_rulings=[],
        final_report=None,
        trace_events=[],
        terminated=False,
        termination_reason="",
    )
