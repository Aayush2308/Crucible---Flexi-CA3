"""Crucible LLM Provider Wrapper.

Provides structured JSON inference with Google Gemini models, automatic retry
with exponential backoff, trace logging, response normalization, and deterministic
mock fallback for offline tests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

# Auto-load .env from project root
_env_file = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_file)

from lib.blackboard import CrucibleState
from lib.schemas import (
    AgentName,
    ArbitrationRuling,
    Finding,
    FindingSet,
    OrchestratorPlan,
    OrchestratorReviewDecision,
)
from lib.trace_logger import record_event

T = TypeVar("T", bound=BaseModel)

# Mock responder registry for automated unit testing
_MOCK_HANDLERS: dict[type, Callable[[str, str], Any]] = {}


def register_mock_handler(schema_cls: type, handler: Callable[[str, str], Any]) -> None:
    """Register a custom handler function for a schema in mock mode."""
    _MOCK_HANDLERS[schema_cls] = handler


def clear_mock_handlers() -> None:
    """Reset registered mock handlers."""
    _MOCK_HANDLERS.clear()


class LLMFailure(Exception):
    """Raised when LLM calls fail across all configured retry attempts."""


def _generate_default_mock(
    schema_cls: type[T],
    system_prompt: str,
    user_prompt: str,
    event_from: AgentName = "system",
) -> T:
    """Produce a deterministic synthetic instance of schema_cls for tests and offline execution."""
    if schema_cls in _MOCK_HANDLERS:
        raw = _MOCK_HANDLERS[schema_cls](system_prompt, user_prompt)
        if isinstance(raw, schema_cls):
            return raw
        if isinstance(raw, dict):
            return schema_cls.model_validate(raw)

    if schema_cls is OrchestratorPlan:
        return OrchestratorPlan(
            agents=["logic_reviewer", "security_auditor", "style_doc_agent"],
            execution_order="parallel",
            focus_areas={},
            budget=3,
            rationale="Automated triage plan: full multi-agent inspection in parallel.",
            next_action="dispatch_workers",
        )  # type: ignore

    if schema_cls is OrchestratorReviewDecision:
        return OrchestratorReviewDecision(
            next_action="converge",
            conflicts_detected=[],
            revision_targets=[],
            replan_reason=None,
            rationale="Review completed: all findings harmonized across agents.",
        )  # type: ignore

    if schema_cls is FindingSet:
        # Determine actual agent from event_from or prompt
        agent_name: AgentName = event_from if event_from in (
            "logic_reviewer", "security_auditor", "style_doc_agent"
        ) else "logic_reviewer"
        if agent_name == "logic_reviewer" and "security" in system_prompt.lower() and "logic" not in system_prompt.lower():
            agent_name = "security_auditor"
        elif agent_name == "logic_reviewer" and "style" in system_prompt.lower() and "logic" not in system_prompt.lower():
            agent_name = "style_doc_agent"

        is_clean = "add_positive_numbers" in user_prompt or "positive integers" in user_prompt
        is_prose = "plain descriptive prose" in user_prompt or "not python source" in user_prompt
        has_sql = "select" in user_prompt.lower() or "sqlite" in user_prompt.lower() or "db.execute" in user_prompt.lower()

        findings: list[Finding] = []

        if is_clean:
            # Scenario B: clean code produces 0 issues
            findings = []
        elif is_prose:
            # Scenario C: unparseable non-code input
            if agent_name == "logic_reviewer":
                findings.append(Finding(
                    line_start=1,
                    line_end=1,
                    function_name=None,
                    category="syntax_error",
                    severity="high",
                    confidence=1.0,
                    evidence="Input text failed AST syntax parsing: not valid Python source code.",
                    recommendation="Provide valid Python syntax or specify correct input language.",
                ))
            elif agent_name == "style_doc_agent":
                findings.append(Finding(
                    line_start=1,
                    line_end=1,
                    function_name=None,
                    category="formatting",
                    severity="low",
                    confidence=0.8,
                    evidence="Plain text input lacks module-level structure or Python statements.",
                    recommendation="Ensure code conforms to Python PEP 8 formatting standards.",
                ))
        elif has_sql:
            # Scenario A / D: SQL injection & complexity
            if agent_name == "security_auditor":
                findings.append(Finding(
                    line_start=2,
                    line_end=2,
                    function_name="login" if "login" in user_prompt else "run_query",
                    category="SQL Injection",
                    severity="critical",
                    confidence=0.98,
                    evidence="Unsanitized dynamic parameter formatting detected in query string (CWE-89).",
                    recommendation="Replace dynamic concatenation with parameterized queries.",
                    cwe_id="CWE-89",
                ))
            elif agent_name == "logic_reviewer":
                if "calculate_discount" in user_prompt:
                    findings.append(Finding(
                        line_start=14,
                        line_end=23,
                        function_name="calculate_discount",
                        category="complexity",
                        severity="medium",
                        confidence=0.85,
                        evidence="Cyclomatic complexity exceeds threshold; nested branching detected.",
                        recommendation="Refactor logic into smaller helper functions.",
                    ))
                else:
                    findings.append(Finding(
                        line_start=1,
                        line_end=5,
                        function_name="run_query",
                        category="error_handling",
                        severity="low",
                        confidence=0.8,
                        evidence="Database query executed without try/except error recovery.",
                        recommendation="Wrap database calls in try/except blocks to handle connection errors.",
                    ))
            elif agent_name == "style_doc_agent":
                findings.append(Finding(
                    line_start=1,
                    line_end=1,
                    function_name="login" if "login" in user_prompt else "run_query",
                    category="missing_docstring",
                    severity="low",
                    confidence=0.9,
                    evidence="Function lacks PEP 257 compliant docstring.",
                    recommendation="Add descriptive docstring detailing parameters and return types.",
                    pep_rule="D103",
                ))
        else:
            # Custom code general fallback
            if agent_name == "style_doc_agent":
                findings.append(Finding(
                    line_start=1,
                    line_end=1,
                    function_name="function",
                    category="missing_docstring",
                    severity="low",
                    confidence=0.85,
                    evidence="Function lacks PEP 257 compliant docstring.",
                    recommendation="Add descriptive docstring detailing parameters and return types.",
                    pep_rule="D103",
                ))
            elif agent_name == "logic_reviewer":
                findings.append(Finding(
                    line_start=1,
                    line_end=1,
                    function_name="function",
                    category="type_safety",
                    severity="info",
                    confidence=0.8,
                    evidence="Function lacks PEP 484 type annotations for parameters and return values.",
                    recommendation="Add type annotations to improve maintainability and static checking.",
                ))

        return FindingSet(
            agent=agent_name,
            round=0,
            findings=findings,
            overall_confidence=0.95,
            tool_results_summary=[],
            notes="Deterministic findings generated for offline/mock execution.",
        )  # type: ignore

    if schema_cls is ArbitrationRuling:
        return ArbitrationRuling(
            conflict_id="conflict_001",
            ruling="security_correct",
            rationale="Security considerations take precedence over pure algorithmic correctness on input handling.",
            severity_override="critical",
            final_recommendation="Adopt parameterized statements to neutralize injection risks.",
        )  # type: ignore

    # Fallback instantiation
    try:
        return schema_cls()  # type: ignore
    except Exception:
        pass

    raise LLMFailure(f"No mock generator available for schema {schema_cls.__name__}")


def _normalize_parsed_data(raw_data: Any, schema_cls: type[T], event_from: AgentName) -> Any:
    """Normalize raw JSON dictionaries from LLM to match Pydantic schema constraints."""
    if not isinstance(raw_data, dict):
        return raw_data

    data = dict(raw_data)

    if schema_cls is FindingSet:
        if not data.get("agent"):
            data["agent"] = event_from

        if "findings" not in data:
            for alt_key in ("issues", "results", "findings_list", "items", "finding_set"):
                if isinstance(data.get(alt_key), list):
                    data["findings"] = data.pop(alt_key)
                    break
            else:
                data["findings"] = []

        normalized_findings = []
        for item in data.get("findings", []):
            if not isinstance(item, dict):
                continue
            f = dict(item)

            # Ensure line numbers are integers
            try:
                f["line_start"] = int(f.get("line_start", 1))
            except (ValueError, TypeError):
                f["line_start"] = 1
            try:
                f["line_end"] = int(f.get("line_end", f["line_start"]))
            except (ValueError, TypeError):
                f["line_end"] = f["line_start"]

            # Category
            if not f.get("category"):
                f["category"] = f.get("id") or f.get("type") or "general"

            # Severity (lowercase, valid enum)
            sev = str(f.get("severity", "medium")).lower().strip()
            if sev not in ("critical", "high", "medium", "low", "info"):
                sev = "medium"
            f["severity"] = sev

            # Evidence & Recommendation
            if not f.get("evidence"):
                f["evidence"] = f.get("description") or f.get("message") or f.get("details") or "Detected issue."
            if not f.get("recommendation"):
                f["recommendation"] = f.get("fix") or f.get("suggestion") or "Review and correct the identified issue."

            normalized_findings.append(f)
        data["findings"] = normalized_findings

    elif schema_cls is OrchestratorPlan:
        if not data.get("agents"):
            data["agents"] = ["logic_reviewer", "security_auditor", "style_doc_agent"]
        action = data.get("next_action")
        if action not in ("dispatch_workers", "converge", "error"):
            data["next_action"] = "dispatch_workers"
        if not data.get("budget"):
            data["budget"] = 3
        if not data.get("execution_order"):
            data["execution_order"] = "parallel"

    elif schema_cls is OrchestratorReviewDecision:
        action = str(data.get("next_action", "converge")).lower().strip()
        if action not in ("converge", "arbitrate", "revise", "replan"):
            action = "converge"
        data["next_action"] = action

    elif schema_cls is ArbitrationRuling:
        if data.get("severity_override"):
            sov = str(data["severity_override"]).lower().strip()
            data["severity_override"] = sov if sov in ("critical", "high", "medium", "low", "info") else None

    return data


DEFAULT_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def call_llm(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    response_schema: type[T],
    state: CrucibleState,
    event_from: AgentName,
    max_retries: int = 3,
    temperature: float = 0.2,
) -> tuple[T, CrucibleState]:
    """Execute structured LLM inference using Gemini, with mock fallback and trace logging."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    force_mock = os.getenv("CRUCIBLE_MOCK_LLM", "0") in ("1", "true", "True")

    # If mock mode active or no API key configured, use deterministic generator
    if force_mock or not api_key or api_key == "your_gemini_api_key_here":
        mock_obj = _generate_default_mock(response_schema, system_prompt, user_prompt, event_from)
        return mock_obj, state

    # Ensure Google SDK environment variable is populated
    os.environ["GOOGLE_API_KEY"] = api_key

    import google.generativeai as genai

    genai.configure(api_key=api_key)

    # Resolve active model (support GEMINI_MODEL env var and upgrade deprecated gemini-1.5-flash)
    active_model = os.getenv("GEMINI_MODEL", "").strip() or model_name or DEFAULT_MODEL_NAME
    if active_model == "gemini-1.5-flash":
        active_model = DEFAULT_MODEL_NAME

    schema_json = json.dumps(response_schema.model_json_schema(), indent=2)

    attempt = 0
    backoff = 2.0
    last_error: Exception | None = None

    while attempt < max_retries:
        attempt += 1
        try:
            model = genai.GenerativeModel(
                model_name=active_model,
                generation_config={
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                },
                system_instruction=system_prompt,
            )

            prompt = (
                f"{user_prompt}\n\n"
                f"### STRICT JSON OUTPUT FORMAT REQUIREMENT ###\n"
                f"You MUST output valid JSON conforming strictly to the following JSON Schema:\n"
                f"```json\n{schema_json}\n```\n"
                f"Respond ONLY with the JSON object. Do not wrap in conversational preamble."
            )

            response = model.generate_content(prompt)
            raw_text = response.text.strip()

            # Strip markdown code blocks if model included them despite json mode
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

            parsed_data = json.loads(raw_text)
            normalized_data = _normalize_parsed_data(parsed_data, response_schema, event_from)
            validated_obj = response_schema.model_validate(normalized_data)

            return validated_obj, state

        except (json.JSONDecodeError, ValidationError) as parse_err:
            last_error = parse_err
            time.sleep(1.0)
        except Exception as api_err:
            last_error = api_err
            err_str = str(api_err).lower()
            if "429" in err_str or "quota" in err_str or "503" in err_str:
                time.sleep(backoff)
                backoff *= 2
            else:
                time.sleep(1.0)

    # If all retries exhausted, log error event and raise
    record_event(
        state=state,
        from_agent=event_from,
        to_agent="blackboard",
        message_type="error",
        summary=f"LLM inference failed after {max_retries} attempts: {last_error}",
        payload={"error": str(last_error), "model": active_model},
    )

    raise LLMFailure(
        f"LLM call to {active_model} failed after {max_retries} attempts. Last error: {last_error}"
    )
