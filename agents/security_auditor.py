"""Crucible Security Auditor Agent.

Author: Anushka Desai (anushkadesai13)
Role: Security Auditor Specialist
Module: agents/security_auditor.py
"""

from __future__ import annotations

import json
from typing import Any

from agents.base import BaseAgent
from lib.blackboard import CrucibleState
from lib.llm_provider import call_llm
from lib.schemas import (
    AgentName,
    CritiqueRequest,
    CritiqueResponse,
    Finding,
    FindingSet,
    ToolCallLog,
)
from lib.trace_logger import record_event
from tools.security_tools import detect_secrets, scan_bandit
from tools.tool_base import run_tool


class SecurityAuditor(BaseAgent):
    """Specialist agent focusing exclusively on vulnerability detection and secret exposure."""

    def __init__(self, agent_name: AgentName = "security_auditor", model_name: str = "gemini-2.5-flash") -> None:
        super().__init__(agent_name=agent_name, model_name=model_name)

    def run(self, state: CrucibleState) -> CrucibleState:
        """Execute security inspection: Bandit SAST & secret scanner first, then LLM structured review."""
        code = state["input_code"]
        language = state["input_language"]
        fault_injection = state.get("fault_injection", "")
        plan = state.get("orchestrator_plan")
        focus = plan.focus_areas.get(self.agent_name, []) if plan else []

        tool_logs: list[ToolCallLog] = []

        # 1. Bandit SAST Tool (supports fault injection for Demo Scenario D)
        bandit_result, state = run_tool(
            tool_fn=scan_bandit,
            code=code,
            tool_name="bandit_scanner",
            fault_injection=fault_injection,
            state=state,
            event_from=self.agent_name,
        )
        tool_logs.append(
            ToolCallLog(
                tool_name="bandit_scanner",
                success=bandit_result.success,
                error=bandit_result.error,
                output_summary=f"Issues: {bandit_result.output.get('issues_count', 0)}" if bandit_result.output else "failed",
                duration_ms=bandit_result.duration_ms,
                fallback_used=bandit_result.fallback_used,
            )
        )

        # 2. Secret Detector Tool
        secret_result, state = run_tool(
            tool_fn=detect_secrets,
            code=code,
            tool_name="secret_detector",
            fault_injection=fault_injection,
            state=state,
            event_from=self.agent_name,
        )
        tool_logs.append(
            ToolCallLog(
                tool_name="secret_detector",
                success=secret_result.success,
                error=secret_result.error,
                output_summary=f"Secrets found: {secret_result.output.get('secrets_found', 0)}" if secret_result.output else "failed",
                duration_ms=secret_result.duration_ms,
                fallback_used=secret_result.fallback_used,
            )
        )

        # 3. LLM Reasoning
        system_prompt = (
            "You are the Security Auditor for Crucible, an autonomous multi-agent code evaluation system.\n"
            "Your ONLY responsibility is to detect security vulnerabilities, unsafe patterns, authorization bypasses,\n"
            "injection flaws (CWE-89, CWE-78), cryptographic weaknesses, and exposed secrets (CWE-798).\n"
            "Tag every finding with its formal CWE identifier where applicable.\n"
            "Do NOT report non-security logical bugs or stylistic/PEP 8 violations.\n"
            "Output strictly valid JSON conforming to the FindingSet schema."
        )

        user_prompt = (
            f"Language: {language}\n"
            f"Context: {state.get('input_context', 'General security inspection')}\n"
            f"Target focus areas: {focus}\n\n"
            f"Static Security Tool Results:\n"
            f"- Bandit SAST Output: {json.dumps(bandit_result.output if bandit_result.success else {'error': bandit_result.error, 'fallback': 'Tool fault or unavailable'})}\n"
            f"- Secret Scanner Output: {json.dumps(secret_result.output if secret_result.success else {'error': secret_result.error})}\n\n"
            f"Source Code:\n{code}"
        )

        finding_set, state = call_llm(
            model_name=self.model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=FindingSet,
            state=state,
            event_from=self.agent_name,
        )

        # Ensure agent metadata and tool logs are preserved
        finding_set.agent = self.agent_name
        finding_set.round = state.get("current_round", 0)
        finding_set.tool_results_summary = tool_logs

        # Append findings to blackboard
        security_findings = state.get("security_findings", [])
        security_findings.append(finding_set)
        state["security_findings"] = security_findings

        record_event(
            state=state,
            from_agent=self.agent_name,
            to_agent="blackboard",
            message_type="finding",
            summary=f"Security Auditor reported {len(finding_set.findings)} findings (confidence: {finding_set.overall_confidence:.2f}).",
            payload=finding_set.model_dump(),
        )

        return state

    def handle_critique(self, state: CrucibleState) -> CrucibleState:
        """Defend or refine security classifications based on inter-agent challenge requests."""
        requests = self.get_my_critique_requests(state)
        if not requests:
            return state

        responses = state.get("critique_responses", [])

        for req in requests:
            all_my_findings = [f for fset in state.get("security_findings", []) for f in fset.findings]
            matched = next((f for f in all_my_findings if f.finding_id == req.challenged_finding_id), None)

            if matched and "style" in req.challenge_reason.lower():
                decision = "reject"
                rationale = (
                    f"Defended finding {req.challenged_finding_id}: "
                    "Although code formatting may be involved, the security implication (unauthenticated access/leak) takes precedence."
                )
                updated = None
            elif matched:
                decision = "revise"
                updated = matched.model_copy()
                updated.severity = "high"
                updated.evidence = f"{matched.evidence} [Security re-verified with note: {req.challenge_reason}]"
                rationale = f"Refined security finding {req.challenged_finding_id} severity based on critique rationale."
            else:
                decision = "reject"
                rationale = f"Security finding {req.challenged_finding_id} remains confirmed as a severe risk."
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
                summary=f"Security Auditor responded to critique: {decision}",
                payload=resp.model_dump(),
                decision_rationale=rationale,
            )

        state["critique_responses"] = responses
        return state
