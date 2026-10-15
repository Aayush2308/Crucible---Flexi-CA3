"""Unit Tests for Style and Documentation Agent & Tools.

Author: Arya Shah (Arya-A-Shah)
Suite: tests/test_style_doc_agent.py
"""

from __future__ import annotations

import pytest

from agents.style_doc_agent import StyleDocAgent
from lib.blackboard import make_initial_state
from lib.schemas import CritiqueRequest, Finding, FindingSet, ReviewRequest
from tools.style_tools import check_pycodestyle, check_pydocstyle


def test_check_pycodestyle_violations(sample_code_scenario_a: str) -> None:
    """Verify pycodestyle detects formatting inconsistencies in sample code."""
    res = check_pycodestyle(sample_code_scenario_a)
    assert res["success"] is True
    # Scenario A has lines lacking docstrings or formatting style notes
    assert "violations" in res


def test_check_pydocstyle_missing_docstrings(sample_code_scenario_a: str) -> None:
    """Verify pydocstyle flags missing module or function docstrings."""
    res = check_pydocstyle(sample_code_scenario_a)
    assert res["success"] is True
    assert res["issues_count"] >= 1
    rules = [i["rule"] for i in res["issues"]]
    # D100 is missing module docstring, D103 is missing function docstring
    assert any(r.startswith("D") for r in rules)


def test_style_doc_agent_run_mock(sample_code_scenario_a: str) -> None:
    """Verify StyleDocAgent runs and appends structured findings to blackboard."""
    req = ReviewRequest(input_code=sample_code_scenario_a, input_language="python")
    state = make_initial_state(req)

    agent = StyleDocAgent()
    updated_state = agent.run(state)

    findings = updated_state["style_findings"]
    assert len(findings) == 1
    assert isinstance(findings[0], FindingSet)
    assert findings[0].agent == "style_doc_agent"
    assert len(findings[0].tool_results_summary) == 2


def test_style_doc_agent_critique_acceptance() -> None:
    """Verify StyleDocAgent defers to critical security or logic findings during critique."""
    req = ReviewRequest(input_code="def query(): pass", input_language="python")
    state = make_initial_state(req)

    style_finding = Finding(
        finding_id="style_001",
        line_start=1,
        line_end=1,
        category="missing_docstring",
        severity="low",
        evidence="Docstring missing",
        recommendation="Add PEP 257 docstring",
        pep_rule="D103",
    )
    state["style_findings"] = [FindingSet(agent="style_doc_agent", findings=[style_finding])]

    challenge = CritiqueRequest(
        critique_id="crit_style_1",
        to_agent="style_doc_agent",
        challenged_finding_id="style_001",
        challenge_reason="This line is undergoing critical security patching; style must defer",
        supporting_evidence="Critical SQL injection repair underway",
    )
    state["critique_requests"] = [challenge]

    agent = StyleDocAgent()
    updated_state = agent.handle_critique(state)

    resp = updated_state["critique_responses"][0]
    assert resp.decision == "accept"
    assert "deferred" in resp.rationale.lower()
