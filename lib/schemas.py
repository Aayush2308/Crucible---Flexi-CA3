"""Crucible Pydantic Data Models & Schemas.

Single source of truth for all data structures exchanged between
agents, tools, API endpoints, and the blackboard.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums / Literal Types
# ---------------------------------------------------------------------------

AgentName = Literal[
    "orchestrator",
    "logic_reviewer",
    "security_auditor",
    "style_doc_agent",
    "system",
]

RecipientName = Literal[
    "orchestrator",
    "logic_reviewer",
    "security_auditor",
    "style_doc_agent",
    "blackboard",
    "user",
    "system",
]

SeverityLevel = Literal[
    "critical",
    "high",
    "medium",
    "low",
    "info",
]

MessageType = Literal[
    "plan",
    "tool_call",
    "tool_result",
    "finding",
    "fallback",
    "review",
    "critique_request",
    "critique_response",
    "arbitration",
    "replan",
    "termination_guard",
    "final_report",
    "error",
]

ConflictStatus = Literal[
    "open",
    "arbitrated",
    "disputed",
]

CritiqueDecision = Literal[
    "accept",
    "revise",
    "reject",
]


# ---------------------------------------------------------------------------
# Tool Results & Logs
# ---------------------------------------------------------------------------

class ToolCallLog(BaseModel):
    """Log record of a single tool invocation."""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str | None = None
    output_summary: str | None = None
    duration_ms: int = 0
    fallback_used: bool = False


class ToolResult(BaseModel):
    """Runtime result returned by tool execution functions in tools/."""
    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None
    fallback_used: bool = False
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Findings & Finding Sets
# ---------------------------------------------------------------------------

class Finding(BaseModel):
    """A single code review issue or observation reported by an agent."""
    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    line_start: int
    line_end: int
    function_name: str | None = None
    category: str
    severity: SeverityLevel
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: str
    recommendation: str
    cwe_id: str | None = None
    pep_rule: str | None = None


class FindingSet(BaseModel):
    """Complete collection of findings returned by an agent for a given round."""
    agent: AgentName
    round: int = 0
    findings: list[Finding] = Field(default_factory=list)
    overall_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tool_results_summary: list[ToolCallLog] = Field(default_factory=list)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Coordination: Conflicts, Critiques & Arbitration
# ---------------------------------------------------------------------------

class Conflict(BaseModel):
    """Disagreement detected between findings from different agents."""
    conflict_id: str = Field(default_factory=lambda: f"conflict_{uuid.uuid4().hex[:6]}")
    agents_involved: list[str]
    finding_ids: list[str]
    line_range: list[int]
    description: str
    status: ConflictStatus = "open"


class CritiqueRequest(BaseModel):
    """Orchestrator request asking a worker to reconsider a specific finding."""
    critique_id: str = Field(default_factory=lambda: f"critique_{uuid.uuid4().hex[:6]}")
    from_agent: Literal["orchestrator"] = "orchestrator"
    to_agent: AgentName
    round: int = 0
    challenged_finding_id: str
    challenge_reason: str
    supporting_evidence: str


class CritiqueResponse(BaseModel):
    """Worker agent response to an Orchestrator challenge."""
    critique_id: str
    from_agent: AgentName
    decision: CritiqueDecision
    rationale: str
    updated_finding: Finding | None = None


class ArbitrationRuling(BaseModel):
    """Binding decision rendered by the Orchestrator resolving a conflict."""
    conflict_id: str
    ruling: Literal[
        "security_correct",
        "logic_correct",
        "style_correct",
        "both_valid_different_aspects",
        "disputed_insufficient_evidence",
    ]
    rationale: str
    severity_override: SeverityLevel | None = None
    final_recommendation: str


# ---------------------------------------------------------------------------
# Orchestrator Decisions & Plans
# ---------------------------------------------------------------------------

class OrchestratorPlan(BaseModel):
    """Triage and execution plan formulated by the Orchestrator."""
    agents: list[AgentName] = Field(
        default_factory=lambda: ["logic_reviewer", "security_auditor", "style_doc_agent"]
    )
    execution_order: str = "parallel"
    focus_areas: dict[str, list[str]] = Field(default_factory=dict)
    budget: int = Field(default=3, ge=1, le=5)
    rationale: str = ""
    next_action: Literal["dispatch_workers", "converge", "error"] = "dispatch_workers"


class OrchestratorReviewDecision(BaseModel):
    """Orchestrator decision following review of worker findings."""
    next_action: Literal["converge", "arbitrate", "revise", "replan"]
    conflicts_detected: list[Conflict] = Field(default_factory=list)
    revision_targets: list[dict[str, Any]] = Field(default_factory=list)
    replan_reason: str | None = None
    rationale: str = ""


# ---------------------------------------------------------------------------
# Trace Event Schema (Category A Primary Evidence)
# ---------------------------------------------------------------------------

class TraceEvent(BaseModel):
    """Audit log entry capturing state transitions, decisions, and tool calls."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    seq: int
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    from_agent: AgentName
    to_agent: RecipientName
    round: int = 0
    message_type: MessageType
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[ToolCallLog] = Field(default_factory=list)
    decision_rationale: str = ""
    replan_trigger: str = ""
    fallback_used: bool = False


# ---------------------------------------------------------------------------
# Final Report & API Payloads
# ---------------------------------------------------------------------------

class FinalReport(BaseModel):
    """Comprehensive final code review synthesis produced by the Orchestrator."""
    run_id: str
    status: Literal["completed", "terminated_max_rounds", "error"] = "completed"
    overall_severity: SeverityLevel = "info"
    executive_summary: str = ""
    all_issues: list[Finding] = Field(default_factory=list)
    resolved_conflicts: list[ArbitrationRuling] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    """Input payload submitted to POST /review."""
    input_code: str
    language: str = "python"
    context: str = ""
    run_id: str | None = None
    fault_injection: str = ""


class ReviewResponse(BaseModel):
    """API response envelope returned after review execution."""
    run_id: str
    status: str
    final_report: FinalReport | None = None


class AutoFixRequest(BaseModel):
    """Input payload submitted to POST /autofix."""
    code: str
    language: str = "python"
    context: str = ""


class AutoFixResponse(BaseModel):
    """API response envelope returned after automated refactor."""
    fixed_code: str
    explanation: str

