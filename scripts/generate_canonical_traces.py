"""Canonical Trace Generator for Crucible Scenarios.

Author: Anushka Desai (anushkadesai13) & Aayush Agarwal (Aayush2308)
Script: scripts/generate_canonical_traces.py

Executes the four standardized demo scenarios (A, B, C, D) through the
LangGraph Orchestrator, saves the full canonical traces in traces/,
and automatically invokes scripts/export_trace.py to produce the
submission-ready text excerpts.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure repo root is on python path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.orchestrator import Orchestrator
from lib.blackboard import make_initial_state
from lib.schemas import ReviewRequest
from lib.trace_logger import flush_trace
from scripts.export_trace import export_trace_excerpt

SCENARIOS = {
    "scenario_a": {
        "title": "Scenario A - SQL Injection & Cyclomatic Complexity",
        "code": (
            "def login(username, password):\n"
            "    query = f\"SELECT * FROM users WHERE username='{username}' AND password='{password}'\"\n"
            "    result = db.execute(query)\n"
            "    user = result.fetchone()\n"
            "    if user:\n"
            "        return {\"token\": generate_token(user.id), \"status\": \"success\"}\n"
            "    return {\"status\": \"failure\"}\n\n"
            "def calculate_discount(items, customer_type):\n"
            "    total = 0\n"
            "    for item in items:\n"
            "        if customer_type == \"premium\":\n"
            "            for sub in item.sub_items:\n"
            "                for detail in sub.details:\n"
            "                    total += detail.price * 0.8\n"
            "        elif customer_type == \"regular\":\n"
            "            total += item.price * 0.9\n"
            "    return total\n"
        ),
        "context": "User authentication and multi-tier pricing calculation",
        "fault_injection": "",
    },
    "scenario_b": {
        "title": "Scenario B - Clean, Idiomatic Python with Docstrings",
        "code": (
            '"""Math utility module for positive arithmetic."""\n\n'
            "def add_positive_numbers(a: int, b: int) -> int:\n"
            '    """Calculate the sum of two positive integers."""\n'
            "    if a < 0 or b < 0:\n"
            '        raise ValueError("Both numbers must be non-negative.")\n'
            "    return a + b\n"
        ),
        "context": "Arithmetic helper utility",
        "fault_injection": "",
    },
    "scenario_c": {
        "title": "Scenario C - Plain Text / Adversarial Non-Code Input",
        "code": "This is plain descriptive prose, not Python source code, submitted to test edge-case input handling.",
        "context": "Adversarial user input testing syntax and AST fallback",
        "fault_injection": "",
    },
    "scenario_d": {
        "title": "Scenario D - Bandit Fault Injection & Autonomous Fallback",
        "code": (
            "import sqlite3\n\n"
            "def run_query(user_id):\n"
            "    # Simulated Bandit failure triggers autonomous LLM reasoning fallback\n"
            '    conn = sqlite3.connect("app.db")\n'
            "    cur = conn.cursor()\n"
            '    cur.execute("SELECT * FROM profiles WHERE id = " + str(user_id))\n'
            "    return cur.fetchall()\n"
        ),
        "context": "Database query service with tool fault injection",
        "fault_injection": "bandit_scanner",
    },
}


def run_and_export_scenarios() -> None:
    """Execute all scenarios, persist traces, and generate submission excerpts."""
    # Ensure mock mode is enabled if no API key is set
    if not os.getenv("GEMINI_API_KEY"):
        os.environ["CRUCIBLE_MOCK_LLM"] = "1"

    traces_dir = REPO_ROOT / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    orch = Orchestrator()

    for key, spec in SCENARIOS.items():
        print(f"\n[Crucible] Running {spec['title']}...")
        req = ReviewRequest(
            input_code=spec["code"],
            language="python",
            context=spec["context"],
            run_id=f"demo_{key}",
            fault_injection=spec["fault_injection"],
        )

        state = make_initial_state(req)
        final_state = orch.run(state)

        # Flush raw trace
        raw_trace_path = traces_dir / f"demo_{key}.json"
        events = [e.model_dump() for e in final_state.get("trace_events", [])]
        with open(raw_trace_path, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)

        print(f"  [OK] Raw trace written: {raw_trace_path} ({len(events)} events)")

        # Export submission excerpt
        excerpt_path = traces_dir / f"{key}_submission_excerpt.txt"
        export_trace_excerpt(str(raw_trace_path), str(excerpt_path), max_chars=12000)
        print(f"  [OK] Submission excerpt generated: {excerpt_path}")

    print("\n[Crucible] All 4 canonical scenario traces generated and exported successfully!")


if __name__ == "__main__":
    run_and_export_scenarios()
