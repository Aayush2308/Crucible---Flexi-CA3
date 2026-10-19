"""Unit Tests for Security Auditor Agent & Tools.

Author: Anushka Desai (anushkadesai13)
Suite: tests/test_security_auditor.py
"""

from __future__ import annotations

import os
import pytest

from agents.security_auditor import SecurityAuditor
from lib.blackboard import make_initial_state
from lib.schemas import CritiqueRequest, Finding, FindingSet, ReviewRequest
from tools.security_tools import detect_secrets, scan_bandit


def test_bandit_scanner_detects_sqli(sample_code_scenario_a: str) -> None:
    """Verify Bandit scanner flags string formatting in SQL queries (B608 / CWE-89)."""
    res = scan_bandit(sample_code_scenario_a)
    assert res["success"] is True
    assert res["issues_count"] >= 1
    cwes = [i.get("cwe_id") for i in res["issues"]]
    test_ids = [i.get("test_id") for i in res["issues"]]
    assert "B608" in test_ids or "CWE-89" in cwes


def test_detect_secrets_scanner(sample_code_secrets: str) -> None:
    """Verify regex secret scanner identifies AWS tokens and JWT strings."""
    res = detect_secrets(sample_code_secrets)
    assert res["success"] is True
    assert res["secrets_found"] >= 2
    patterns = [f["pattern"] for f in res["findings"]]
    assert "aws_access_key" in patterns or "jwt_token" in patterns


def test_security_auditor_run_mock(sample_code_scenario_a: str) -> None:
    """Verify SecurityAuditor runs and registers security findings in blackboard."""
    req = ReviewRequest(input_code=sample_code_scenario_a, input_language="python")
    state = make_initial_state(req)

    agent = SecurityAuditor()
    updated_state = agent.run(state)

    findings = updated_state["security_findings"]
    assert len(findings) == 1
    assert isinstance(findings[0], FindingSet)
    assert findings[0].agent == "security_auditor"
    assert len(findings[0].tool_results_summary) == 2


def test_security_auditor_fault_injection_fallback(sample_code_scenario_a: str) -> None:
    """Verify fault injection on bandit tool triggers fallback without crashing (Category C2)."""
    req = ReviewRequest(input_code=sample_code_scenario_a, input_language="python")
    state = make_initial_state(req)
    state["fault_injection"] = "bandit_scanner"

    agent = SecurityAuditor()
    updated_state = agent.run(state)

    # Bandit failed due to simulated fault, but agent continued via LLM reasoning
    tool_summary = updated_state["security_findings"][0].tool_results_summary
    bandit_log = next((t for t in tool_summary if t.tool_name == "bandit_scanner"), None)
    assert bandit_log is not None
    assert bandit_log.success is False
    assert bandit_log.fallback_used is True

    # State still contains security findings
    assert len(updated_state["security_findings"]) == 1


def test_security_auditor_critique_response() -> None:
    """Verify SecurityAuditor defends critical security findings against style downgrade."""
    req = ReviewRequest(input_code="def query(): pass", input_language="python")
    state = make_initial_state(req)

    vuln_finding = Finding(
        finding_id="sec_001",
        line_start=2,
        line_end=2,
        category="injection",
        severity="critical",
        evidence="Raw SQL injection",
        recommendation="Use parameters",
        cwe_id="CWE-89",
    )
    state["security_findings"] = [FindingSet(agent="security_auditor", findings=[vuln_finding])]

    challenge = CritiqueRequest(
        critique_id="crit_sec_1",
        to_agent="security_auditor",
        challenged_finding_id="sec_001",
        challenge_reason="This looks like a style issue of line length",
        supporting_evidence="Exceeds 79 characters",
    )
    state["critique_requests"] = [challenge]

    agent = SecurityAuditor()
    updated_state = agent.handle_critique(state)

    resp = updated_state["critique_responses"][0]
    assert resp.decision == "reject"
    assert "takes precedence" in resp.rationale
