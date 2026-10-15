"""Crucible Structured Trace Logger.

Provides event generation, appending to the shared CrucibleState blackboard,
and mechanical persistence to the traces/ directory on disk.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.blackboard import CrucibleState
from lib.schemas import AgentName, MessageType, RecipientName, ToolCallLog, TraceEvent


def make_event(
    state: CrucibleState,
    from_agent: AgentName,
    to_agent: RecipientName,
    message_type: MessageType,
    summary: str,
    payload: dict[str, Any] | None = None,
    tool_calls: list[ToolCallLog] | None = None,
    decision_rationale: str = "",
    replan_trigger: str = "",
    fallback_used: bool = False,
) -> TraceEvent:
    """Create a new TraceEvent instance populated with current state context."""
    seq = state.get("seq_counter", 0) + 1
    state["seq_counter"] = seq

    return TraceEvent(
        event_id=str(uuid.uuid4()),
        run_id=state.get("run_id", "unknown_run"),
        seq=seq,
        timestamp=datetime.now(timezone.utc).isoformat(),
        from_agent=from_agent,
        to_agent=to_agent,
        round=state.get("current_round", 0),
        message_type=message_type,
        summary=summary,
        payload=payload or {},
        tool_calls=tool_calls or [],
        decision_rationale=decision_rationale,
        replan_trigger=replan_trigger,
        fallback_used=fallback_used,
    )


def emit_event(state: CrucibleState, event: TraceEvent) -> CrucibleState:
    """Append a TraceEvent to the blackboard trace log."""
    if "trace_events" not in state or state["trace_events"] is None:
        state["trace_events"] = []
    state["trace_events"].append(event)
    return state


def record_event(
    state: CrucibleState,
    from_agent: AgentName,
    to_agent: RecipientName,
    message_type: MessageType,
    summary: str,
    payload: dict[str, Any] | None = None,
    tool_calls: list[ToolCallLog] | None = None,
    decision_rationale: str = "",
    replan_trigger: str = "",
    fallback_used: bool = False,
) -> tuple[TraceEvent, CrucibleState]:
    """Convenience helper to create and append an event in a single call."""
    event = make_event(
        state=state,
        from_agent=from_agent,
        to_agent=to_agent,
        message_type=message_type,
        summary=summary,
        payload=payload,
        tool_calls=tool_calls,
        decision_rationale=decision_rationale,
        replan_trigger=replan_trigger,
        fallback_used=fallback_used,
    )
    emit_event(state, event)
    return event, state


def flush_trace(
    state: CrucibleState,
    trace_dir: str | Path = "traces",
) -> Path:
    """Serialize and flush all trace events for this run to disk."""
    dir_path = Path(trace_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    run_id = state.get("run_id", "unknown_run")
    target_path = dir_path / f"{run_id}.json"

    events = [event.model_dump() for event in state.get("trace_events", [])]

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

    return target_path
