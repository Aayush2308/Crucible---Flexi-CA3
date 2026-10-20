"""Crucible FastAPI Application Server.

Primary Owner: Aayush Agarwal (Aayush2308)
Module: api/main.py

Endpoints:
  GET  /health                      — Liveness probe (used by Render.com & warmup script)
  POST /review                      — Execute full orchestrator graph, return JSON response
  GET  /review/stream/{run_id}      — Server-Sent Events (SSE) stream of live trace events
  GET  /                            — Serve the web UI (ui/index.html)
  GET  /{path}                      — Serve static UI assets (style.css, app.js)
"""

from __future__ import annotations

# Load .env file automatically (local dev) — no-op if file doesn't exist
from dotenv import load_dotenv
load_dotenv()

import asyncio
from contextlib import asynccontextmanager
import json
import os
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agents.orchestrator import Orchestrator
from lib.blackboard import make_initial_state
from lib.schemas import FinalReport, ReviewRequest, ReviewResponse, TraceEvent
from lib.trace_logger import flush_trace

# ---------------------------------------------------------------------------
# App Initialisation & Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    mock = os.getenv("CRUCIBLE_MOCK_LLM", "0") in ("1", "true", "True")
    print(f"[Crucible] Server starting — mock_mode={mock}")
    print(f"[Crucible] UI served from: {UI_DIR}")
    print(f"[Crucible] Docs available at: /docs")
    yield
    print("[Crucible] Server shutting down.")


app = FastAPI(
    title="Crucible — Multi-Agent Code Review API",
    description=(
        "Autonomous multi-agent code review system powered by LangGraph and Gemini. "
        "Agents: LogicReviewer, SecurityAuditor, StyleDocAgent, Orchestrator."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store: run_id → list of SSE events as JSON strings
# This is intentionally simple for the CA3 scope (single-server deployment)
_run_event_store: dict[str, list[str]] = {}
_run_completed: dict[str, bool] = {}
_run_final_report: dict[str, FinalReport | None] = {}

# Path to ui/ directory relative to project root
UI_DIR = Path(__file__).parent.parent / "ui"


# ---------------------------------------------------------------------------
# Static File Serving — UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui() -> FileResponse:
    """Serve the Crucible web dashboard."""
    index_path = UI_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI not found. Check ui/index.html exists.")
    return FileResponse(str(index_path), media_type="text/html")


@app.get("/style.css", include_in_schema=False)
async def serve_css() -> FileResponse:
    return FileResponse(str(UI_DIR / "style.css"), media_type="text/css")


@app.get("/app.js", include_in_schema=False)
async def serve_js() -> FileResponse:
    return FileResponse(str(UI_DIR / "app.js"), media_type="application/javascript")


# ---------------------------------------------------------------------------
# GET /health — Liveness probe
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
async def health_check() -> JSONResponse:
    """Liveness probe for Render.com health checks and warmup script."""
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "crucible",
            "version": "1.0.0",
            "mock_mode": os.getenv("CRUCIBLE_MOCK_LLM", "0") in ("1", "true", "True"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )


# ---------------------------------------------------------------------------
# POST /review — Execute orchestrator graph (sync, returns full result)
# ---------------------------------------------------------------------------

@app.post("/review", response_model=ReviewResponse, tags=["Review"])
async def run_review(payload: ReviewRequest) -> JSONResponse:
    """
    Execute the full multi-agent code review pipeline.

    Accepts a ReviewRequest JSON body and runs the complete LangGraph
    orchestration (triage → dispatch → conflict detection → peer critique
    → arbitration → synthesis). Returns all trace events and final report.

    Set CRUCIBLE_MOCK_LLM=1 to run without a Gemini API key.
    """
    run_id = payload.run_id or f"run_{uuid.uuid4().hex[:8]}"
    payload.run_id = run_id

    # Initialise SSE store for this run
    _run_event_store[run_id] = []
    _run_completed[run_id] = False
    _run_final_report[run_id] = None

    # Build initial blackboard state
    state = make_initial_state(payload)

    try:
        # Run the LangGraph orchestrator (blocking; fine for async FastAPI via threadpool)
        orch = Orchestrator()
        final_state = await asyncio.get_event_loop().run_in_executor(None, orch.run, state)
    except Exception as exc:
        _run_completed[run_id] = True
        raise HTTPException(status_code=500, detail=f"Orchestrator execution failed: {exc}")

    # Store events for SSE streaming endpoint
    trace_events: list[TraceEvent] = final_state.get("trace_events", [])
    for event in trace_events:
        _run_event_store[run_id].append(json.dumps(event.model_dump()))

    # Store final report
    final_report: FinalReport | None = final_state.get("final_report")
    _run_final_report[run_id] = final_report
    _run_completed[run_id] = True

    # Persist trace to disk
    try:
        flush_trace(final_state, trace_dir="traces")
    except Exception:
        pass  # Non-fatal: trace flush failure should not break the response

    # Build response — UI expects: {run_id, status, events, final_report}
    events_payload = [event.model_dump() for event in trace_events]

    # Normalise final_report fields for UI compatibility
    report_payload: dict | None = None
    if final_report:
        report_payload = {
            "run_id": final_report.run_id,
            "status": final_report.status,
            "overall_severity": final_report.overall_severity,
            "overall_verdict": (
                "critical_issues_found"
                if final_report.overall_severity in ("critical", "high")
                else "review_complete"
            ),
            "executive_summary": final_report.executive_summary,
            "synthesis_summary": final_report.executive_summary,
            "all_issues": [f.model_dump() for f in final_report.all_issues],
            "ranked_findings": [f.model_dump() for f in final_report.all_issues],
            "resolved_conflicts": [r.model_dump() for r in final_report.resolved_conflicts],
            "metrics": final_report.metrics,
        }

    return JSONResponse(
        content={
            "run_id": run_id,
            "status": "completed",
            "events": events_payload,
            "final_report": report_payload,
        }
    )


# ---------------------------------------------------------------------------
# GET /review/stream/{run_id} — Server-Sent Events (SSE) real-time stream
# ---------------------------------------------------------------------------

async def _sse_event_generator(run_id: str) -> AsyncGenerator[str, None]:
    """
    Yield trace events for a specific run_id as SSE formatted strings.

    The generator polls the in-memory event store until the run is marked
    complete, then sends a final 'done' event to signal stream completion.
    """
    cursor = 0
    max_wait_s = 120  # 2 minute timeout
    elapsed = 0.0
    poll_interval = 0.1  # 100ms polling

    while elapsed < max_wait_s:
        events = _run_event_store.get(run_id, [])

        # Stream any new events since last cursor position
        while cursor < len(events):
            payload = events[cursor]
            yield f"data: {payload}\n\n"
            cursor += 1

        # Check if run is complete
        if _run_completed.get(run_id, False) and cursor >= len(events):
            # Send final_report as a synthetic SSE event
            report = _run_final_report.get(run_id)
            if report:
                report_event = {
                    "message_type": "final_report",
                    "from_agent": "orchestrator",
                    "to_agent": "user",
                    "summary": report.executive_summary,
                    "final_report": {
                        "overall_severity": report.overall_severity,
                        "overall_verdict": (
                            "critical_issues_found"
                            if report.overall_severity in ("critical", "high")
                            else "review_complete"
                        ),
                        "synthesis_summary": report.executive_summary,
                        "ranked_findings": [f.model_dump() for f in report.all_issues],
                    },
                }
                yield f"data: {json.dumps(report_event)}\n\n"

            # Signal stream completion
            yield "data: {\"message_type\": \"stream_done\"}\n\n"
            break

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    if elapsed >= max_wait_s:
        yield "data: {\"message_type\": \"error\", \"summary\": \"SSE stream timeout — run took too long.\"}\n\n"


@app.get("/review/stream/{run_id}", tags=["Review"])
async def stream_review_events(run_id: str, request: Request) -> StreamingResponse:
    """
    Stream real-time trace events for an ongoing or completed review run.

    Connect after POSTing to /review. Each SSE event is a JSON-encoded
    TraceEvent from the LangGraph blackboard.

    Usage (JavaScript):
      const es = new EventSource(`/review/stream/${run_id}`);
      es.onmessage = e => console.log(JSON.parse(e.data));
    """
    if run_id not in _run_event_store and run_id not in _run_completed:
        # Start a blank entry so the generator doesn't immediately fail
        _run_event_store[run_id] = []
        _run_completed[run_id] = False

    return StreamingResponse(
        _sse_event_generator(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# GET /review/{run_id} — Retrieve a completed run's result
# ---------------------------------------------------------------------------

@app.get("/review/{run_id}", tags=["Review"])
async def get_review_result(run_id: str) -> JSONResponse:
    """Retrieve the stored result for a previously completed review run."""
    if run_id not in _run_completed:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    if not _run_completed.get(run_id):
        return JSONResponse(content={"run_id": run_id, "status": "in_progress"})

    report = _run_final_report.get(run_id)
    events = _run_event_store.get(run_id, [])

    return JSONResponse(
        content={
            "run_id": run_id,
            "status": "completed",
            "event_count": len(events),
            "final_report": json.loads(report.model_dump_json()) if report else None,
        }
    )



