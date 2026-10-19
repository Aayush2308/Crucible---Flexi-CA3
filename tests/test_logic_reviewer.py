"""Unit Tests for Logic Reviewer Agent & Tools.

Author: Anum Agarwal (anum777)
Suite: tests/test_logic_reviewer.py
"""

from __future__ import annotations

import pytest

from agents.logic_reviewer import LogicReviewer
from lib.blackboard import make_initial_state
from lib.schemas import CritiqueRequest, Finding, FindingSet, ReviewRequest
from tools.logic_tools import analyze_ast, compute_complexity


def test_ast_analyzer_valid_code(sample_code_scenario_a: str) -> None:
    """Verify AST tool extracts function definitions and tracks nesting depth."""
    res = analyze_ast(sample_code_scenario_a)
    assert res["valid"] is True
    func_names = [f["name"] for f in res["functions"]]
    assert "login" in func_names
    assert "calculate_discount" in func_names
    assert res["max_nesting_depth"] >= 3


def test_ast_analyzer_syntax_error(sample_code_scenario_c: str) -> None:
    """Verify AST analyzer fails gracefully on non-Python input without crashing."""
    res = analyze_ast(sample_code_scenario_c)
    assert res["valid"] is False
    assert "SyntaxError" in res["error"]


def test_complexity_scorer_calculation(sample_code_scenario_a: str) -> None:
    """Verify radon cyclomatic complexity analysis produces structured ranks."""
    res = compute_complexity(sample_code_scenario_a)
    assert res["success"] is True
    assert len(res["blocks"]) >= 2
    for b in res["blocks"]:
        assert "complexity" in b
        assert "rank" in b


def test_logic_reviewer_run_mock(sample_code_scenario_a: str) -> None:
    """Verify LogicReviewer executes in mock mode and populates blackboard findings."""
    req = ReviewRequest(input_code=sample_code_scenario_a, input_language="python")
    state = make_initial_state(req)

    agent = LogicReviewer()
    updated_state = agent.run(state)

    findings = updated_state["logic_findings"]
    assert len(findings) == 1
    assert isinstance(findings[0], FindingSet)
    assert findings[0].agent == "logic_reviewer"
    assert len(findings[0].tool_results_summary) == 2


def test_logic_reviewer_handle_critique() -> None:
    """Verify critique resolution logic responds properly to Orchestrator challenges."""
    req = ReviewRequest(input_code="def foo(): pass", input_language="python")
    state = make_initial_state(req)

    sample_finding = Finding(
        finding_id="finding_123",
        line_start=1,
        line_end=1,
        category="bug",
        severity="high",
        evidence="Issue noted",
        recommendation="Fix bug",
    )
    state["logic_findings"] = [FindingSet(agent="logic_reviewer", findings=[sample_finding])]

    challenge = CritiqueRequest(
        critique_id="crit_001",
        to_agent="logic_reviewer",
        challenged_finding_id="finding_123",
        challenge_reason="This is security related",
        supporting_evidence="Matches SQL injection pattern",
    )
    state["critique_requests"] = [challenge]

    agent = LogicReviewer()
    updated_state = agent.handle_critique(state)

    responses = updated_state["critique_responses"]
    assert len(responses) == 1
    assert responses[0].decision == "accept"
