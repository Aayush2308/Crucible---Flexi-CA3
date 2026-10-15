"""Crucible Tool Execution Base Framework.

Provides the standardized run_tool execution harness with timing, exception containment,
deterministic fault-injection for Category C2 robustness grading, and trace event emission.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

from lib.blackboard import CrucibleState
from lib.schemas import AgentName, ToolCallLog, ToolResult
from lib.trace_logger import record_event


class ToolFaultInjected(Exception):
    """Exception raised when a tool failure is artificially simulated via fault injection."""


def run_tool(
    tool_fn: Callable[[str], Any],
    code: str,
    tool_name: str,
    fault_injection: str,
    state: CrucibleState,
    event_from: AgentName,
    timeout_s: int = 10,
) -> tuple[ToolResult, CrucibleState]:
    """Execute a static analysis tool under monitored conditions.

    1. Checks if fault_injection or CRUCIBLE_FAULT env var matches tool_name.
    2. Emits a 'tool_call' TraceEvent before running.
    3. Executes tool_fn(code) with exception containment.
    4. Emits a 'tool_result' (or 'fallback' if failed) TraceEvent.
    5. Returns a structured (ToolResult, updated_state) tuple.
    """
    env_fault = os.getenv("CRUCIBLE_FAULT", "").strip()
    target_fault = fault_injection.strip() or env_fault

    # 1. Emit tool_call event
    record_event(
        state=state,
        from_agent=event_from,
        to_agent="blackboard",
        message_type="tool_call",
        summary=f"Invoking tool: {tool_name}",
        payload={"tool_name": tool_name},
    )

    # 2. Check for artificial fault injection
    if target_fault and target_fault.lower() == tool_name.lower():
        fallback_log = ToolCallLog(
            tool_name=tool_name,
            success=False,
            error=f"Simulated fault injection: {tool_name}",
            fallback_used=True,
            duration_ms=0,
        )

        record_event(
            state=state,
            from_agent=event_from,
            to_agent="blackboard",
            message_type="fallback",
            summary=f"Fault injected on {tool_name}; agent falling back to LLM-only reasoning.",
            payload={"tool_name": tool_name, "reason": "fault_injection"},
            tool_calls=[fallback_log],
            fallback_used=True,
        )

        result = ToolResult(
            tool_name=tool_name,
            success=False,
            output=None,
            error=f"Fault injected on {tool_name}",
            fallback_used=True,
            duration_ms=0,
        )
        return result, state

    # 3. Execute tool function safely
    start_time = time.perf_counter()
    try:
        output = tool_fn(code)
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        tool_log = ToolCallLog(
            tool_name=tool_name,
            success=True,
            error=None,
            output_summary=str(output)[:200] if output else "completed",
            duration_ms=duration_ms,
            fallback_used=False,
        )

        record_event(
            state=state,
            from_agent=event_from,
            to_agent="blackboard",
            message_type="tool_result",
            summary=f"Tool {tool_name} completed in {duration_ms}ms.",
            payload={"output": output},
            tool_calls=[tool_log],
        )

        result = ToolResult(
            tool_name=tool_name,
            success=True,
            output=output,
            error=None,
            fallback_used=False,
            duration_ms=duration_ms,
        )
        return result, state

    except Exception as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        err_msg = f"{type(e).__name__}: {e}"

        tool_log = ToolCallLog(
            tool_name=tool_name,
            success=False,
            error=err_msg,
            duration_ms=duration_ms,
            fallback_used=True,
        )

        record_event(
            state=state,
            from_agent=event_from,
            to_agent="blackboard",
            message_type="fallback",
            summary=f"Tool {tool_name} failed ({err_msg}); falling back to LLM analysis.",
            payload={"error": err_msg, "tool_name": tool_name},
            tool_calls=[tool_log],
            fallback_used=True,
        )

        result = ToolResult(
            tool_name=tool_name,
            success=False,
            output=None,
            error=err_msg,
            fallback_used=True,
            duration_ms=duration_ms,
        )
        return result, state
