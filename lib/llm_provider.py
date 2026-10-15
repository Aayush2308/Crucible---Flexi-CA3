"""Crucible LLM Provider Wrapper.

Provides structured JSON inference with Google Gemini models, automatic retry
with exponential backoff, trace logging, and deterministic mock fallback for offline tests.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, TypeVar
from pydantic import BaseModel, ValidationError

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


def _generate_default_mock(schema_cls: type[T], system_prompt: str, user_prompt: str) -> T:
    """Produce a deterministic synthetic instance of schema_cls for tests."""
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
        agent_name: AgentName = "logic_reviewer"
        if "security" in system_prompt.lower():
            agent_name = "security_auditor"
            sample_finding = Finding(
                line_start=1,
                line_end=5,
                function_name="login",
                category="injection",
                severity="critical",
                confidence=0.95,
                evidence="Unsanitized dynamic parameter formatting detected in query string.",
                recommendation="Replace dynamic concatenation with parameterized queries.",
                cwe_id="CWE-89",
            )
        elif "style" in system_prompt.lower():
            agent_name = "style_doc_agent"
            sample_finding = Finding(
                line_start=1,
                line_end=1,
                function_name="login",
                category="missing_docstring",
                severity="low",
                confidence=0.9,
                evidence="Function 'login' lacks PEP 257 compliant docstring.",
                recommendation="Add descriptive docstring detailing parameters and return types.",
                pep_rule="D103",
            )
        else:
            sample_finding = Finding(
                line_start=1,
                line_end=10,
                function_name="login",
                category="complexity",
                severity="medium",
                confidence=0.85,
                evidence="Cyclomatic complexity exceeds threshold; nested branching detected.",
                recommendation="Refactor logic into smaller helper functions.",
            )
        return FindingSet(
            agent=agent_name,
            round=0,
            findings=[sample_finding],
            overall_confidence=0.9,
            tool_results_summary=[],
            notes="Mock findings generated for offline execution.",
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
    api_key = os.getenv("GEMINI_API_KEY", "")
    force_mock = os.getenv("CRUCIBLE_MOCK_LLM", "0") in ("1", "true", "True")

    # If mock mode active or no API key configured, use deterministic generator
    if force_mock or not api_key or api_key == "your_gemini_api_key_here":
        mock_obj = _generate_default_mock(response_schema, system_prompt, user_prompt)
        return mock_obj, state

    import google.generativeai as genai

    genai.configure(api_key=api_key)

    attempt = 0
    backoff = 2.0
    last_error: Exception | None = None

    while attempt < max_retries:
        attempt += 1
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                },
                system_instruction=system_prompt,
            )

            prompt = (
                f"{user_prompt}\n\n"
                f"Respond ONLY with valid JSON conforming to the schema of {response_schema.__name__}."
            )

            response = model.generate_content(prompt)
            raw_text = response.text.strip()

            # Strip markdown code blocks if model included them despite json mode
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

            parsed_data = json.loads(raw_text)
            validated_obj = response_schema.model_validate(parsed_data)

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
        payload={"error": str(last_error), "model": model_name},
    )

    raise LLMFailure(
        f"LLM call to {model_name} failed after {max_retries} attempts. Last error: {last_error}"
    )
