
"""Crucible Style and Documentation Agent.

Author: Arya Shah (Arya-A-Shah)
Role: Style & Doc Specialist
Module: agents/style_doc_agent.py
"""

from __future__ import annotations

import json
from typing import Any

from agents.base import BaseAgent
from lib.blackboard import CrucibleState
from lib.llm_provider import LLMFailure, call_llm
from lib.schemas import (
    AgentName,
    CritiqueRequest,
    CritiqueResponse,
    Finding,
    FindingSet,
    ToolCallLog,
)
from lib.trace_logger import record_event
from tools.style_tools import check_pycodestyle, check_pydocstyle
from tools.tool_base import run_tool


class StyleDocAgent(BaseAgent):
    """Specialist agent focusing exclusively on PEP 8 formatting, naming, and docstring coverage."""

    def __init__(self, agent_name: AgentName = "style_doc_agent", model_name: str = "gemini-2.5-flash") -> None:
        super().__init__(agent_name=agent_name, model_name=model_name)

    def run(self, state: CrucibleState) -> CrucibleState:
        """Execute style & doc inspection: pycodestyle & pydocstyle first, then LLM structured review."""
        code = state["input_code"]
        language = state["input_language"]
        fault_injection = state.get("fault_injection", "")
        plan = state.get("orchestrator_plan")
        focus = plan.focus_areas.get(self.agent_name, []) if plan else []

        tool_logs: list[ToolCallLog] = []

        # 1. pycodestyle PEP 8 Tool
        style_result, state = run_tool(
            tool_fn=check_pycodestyle,
            code=code,
            tool_name="style_checker",
            fault_injection=fault_injection,
            state=state,
            event_from=self.agent_name,
        )
        tool_logs.append(
            ToolCallLog(
                tool_name="style_checker",
                success=style_result.success,
                error=style_result.error,
                output_summary=f"Violations: {style_result.output.get('violations_count', 0)}" if style_result.output else "failed",
                duration_ms=style_result.duration_ms,
                fallback_used=style_result.fallback_used,
            )
        )

        # 2. pydocstyle Docstring Tool
        doc_result, state = run_tool(
            tool_fn=check_pydocstyle,
            code=code,
            tool_name="docstring_checker",
            fault_injection=fault_injection,
            state=state,
            event_from=self.agent_name,
        )
        tool_logs.append(
            ToolCallLog(
                tool_name="docstring_checker",
                success=doc_result.success,
                error=doc_result.error,
                output_summary=f"Docstring issues: {doc_result.output.get('issues_count', 0)}" if doc_result.output else "failed",
                duration_ms=doc_result.duration_ms,
                fallback_used=doc_result.fallback_used,
            )
        )

        # 3. LLM Reasoning
        system_prompt = (
            "You are the Style & Documentation Agent for Crucible, an autonomous multi-agent code evaluation system.\n"
            "Your ONLY responsibility is to analyze code formatting, language idiomatic standards (PEP 8 for Python, ESLint/camelCase for JavaScript, gofmt/Effective Go for Go),\n"
            "naming conventions, and documentation completeness (PEP 257 docstrings for Python, JSDoc for JavaScript, Go doc comments for Go).\n"
            "Do NOT report security vulnerabilities or pure algorithmic bugs.\n"
            "Output strictly valid JSON conforming to the FindingSet schema."
        )

        user_prompt = (
            f"Language: {language}\n"
            f"Context: {state.get('input_context', 'General style inspection')}\n"
            f"Target focus areas: {focus}\n\n"
            f"Static Style Tool Results:\n"
            f"- pycodestyle (PEP 8) output: {json.dumps(style_result.output if style_result.success else {'error': style_result.error})}\n"
            f"- pydocstyle output: {json.dumps(doc_result.output if doc_result.success else {'error': doc_result.error})}\n\n"
            f"Source Code:\n{code}"
        )

        try:
            finding_set, state = call_llm(
                model_name=self.model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=FindingSet,
                state=state,
                event_from=self.agent_name,
            )
        except LLMFailure as llm_err:
            fallback_findings = []
            if doc_result.success and doc_result.output:
                for missing in doc_result.output.get("missing_docstrings", []):
                    fallback_findings.append(Finding(
                        line_start=missing.get("line", 1),
                        line_end=missing.get("line", 1),
                        function_name=missing.get("name"),
                        category="missing_docstring",
                        severity="low",
                        confidence=0.9,
                        evidence=f"Object '{missing.get('name')}' is missing a docstring (PEP 257).",
                        recommendation="Add descriptive docstring detailing parameters and return types.",
                        pep_rule="D103",
                    ))
            if style_result.success and style_result.output:
                for viol in style_result.output.get("violations", []):
                    fallback_findings.append(Finding(
                        line_start=viol.get("line", 1),
                        line_end=viol.get("line", 1),
                        function_name=None,
                        category="pep8_formatting",
                        severity="low",
                        confidence=0.85,
                        evidence=viol.get("message", "PEP 8 style violation"),
                        recommendation="Format code according to PEP 8 guidelines.",
                        pep_rule=viol.get("code"),
                    ))
            if not fallback_findings:
                from lib.llm_provider import _generate_default_mock
                mock_set = _generate_default_mock(FindingSet, system_prompt, user_prompt, self.agent_name)
                fallback_findings = mock_set.findings

            finding_set = FindingSet(
                agent=self.agent_name,
                round=state.get("current_round", 0),
                findings=fallback_findings,
                overall_confidence=0.85,
                tool_results_summary=tool_logs,
                notes=f"Fallback findings derived from pycodestyle and pydocstyle tools: {llm_err}",
            )

        # Ensure agent metadata and tool logs are preserved
        finding_set.agent = self.agent_name
        finding_set.round = state.get("current_round", 0)
        finding_set.tool_results_summary = tool_logs

        # Append findings to blackboard
        style_findings = state.get("style_findings", [])
        style_findings.append(finding_set)
        state["style_findings"] = style_findings

        record_event(
            state=state,
            from_agent=self.agent_name,
            to_agent="blackboard",
            message_type="finding",
            summary=f"Style & Doc Agent reported {len(finding_set.findings)} findings (confidence: {finding_set.overall_confidence:.2f}).",
            payload=finding_set.model_dump(),
        )

        return state

    def handle_critique(self, state: CrucibleState) -> CrucibleState:
        """Handle challenge requests regarding stylistic versus logic/security considerations."""
        requests = self.get_my_critique_requests(state)
        if not requests:
            return state

        responses = state.get("critique_responses", [])

        for req in requests:
            all_my_findings = [f for fset in state.get("style_findings", []) for f in fset.findings]
            matched = next((f for f in all_my_findings if f.finding_id == req.challenged_finding_id), None)

            # Style concerns normally defer gracefully to security or severe logic bugs
            if matched and ("security" in req.challenge_reason.lower() or "critical" in req.challenge_reason.lower()):
                decision = "accept"
                rationale = (
                    f"Accepted challenge on {req.challenged_finding_id}: "
                    "Style observation deferred to higher-priority architectural or security constraints."
                )
                updated = None
            elif matched:
                decision = "revise"
                updated = matched.model_copy()
                updated.severity = "info"
                updated.evidence = f"{matched.evidence} [Downgraded following critique: {req.challenge_reason}]"
                rationale = f"Downgraded finding {req.challenged_finding_id} severity to info after peer critique."
            else:
                decision = "reject"
                rationale = f"Stylistic rule for {req.challenged_finding_id} remains valid as a quality recommendation."
                updated = None

            resp = CritiqueResponse(
                critique_id=req.critique_id,
                from_agent=self.agent_name,
                decision=decision,
                rationale=rationale,
                updated_finding=updated,
            )
            responses.append(resp)

            record_event(
                state=state,
                from_agent=self.agent_name,
                to_agent="orchestrator",
                message_type="critique_response",
                summary=f"Style & Doc Agent responded to critique: {decision}",
                payload=resp.model_dump(),
                decision_rationale=rationale,
            )

        state["critique_responses"] = responses
        return state
