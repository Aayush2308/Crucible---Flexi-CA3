"""Crucible Base Agent Abstract Class.

All specialized agents (LogicReviewer, SecurityAuditor, StyleDocAgent, Orchestrator)
inherit from BaseAgent to ensure consistent invocation contracts across LangGraph nodes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from lib.blackboard import CrucibleState
from lib.schemas import AgentName, CritiqueRequest, CritiqueResponse
from lib.trace_logger import record_event


class BaseAgent(ABC):
    """Abstract Base Class for Crucible Multi-Agent Components."""

    agent_name: AgentName
    model_name: str

    def __init__(self, agent_name: AgentName, model_name: str) -> None:
        self.agent_name = agent_name
        self.model_name = model_name

    @abstractmethod
    def run(self, state: CrucibleState) -> CrucibleState:
        """Primary execution method invoked as a LangGraph node.

        Reads relevant data from the blackboard, invokes tools, executes
        LLM reasoning, writes findings back, and returns the updated state.
        """
        raise NotImplementedError

    def get_my_critique_requests(self, state: CrucibleState) -> list[CritiqueRequest]:
        """Extract critique challenges targeted specifically at this agent."""
        all_requests = state.get("critique_requests", [])
        return [req for req in all_requests if req.to_agent == self.agent_name]

    def handle_critique(self, state: CrucibleState) -> CrucibleState:
        """Default handler for inter-agent critique challenges.

        Subclasses may override this to tailor revision logic and updated findings.
        """
        requests = self.get_my_critique_requests(state)
        if not requests:
            return state

        responses = state.get("critique_responses", [])

        for req in requests:
            # Default response: accept challenge with a generic rationale if not overridden
            response = CritiqueResponse(
                critique_id=req.critique_id,
                from_agent=self.agent_name,
                decision="accept",
                rationale=f"Agent {self.agent_name} accepted critique regarding finding {req.challenged_finding_id}.",
                updated_finding=None,
            )
            responses.append(response)

            record_event(
                state=state,
                from_agent=self.agent_name,
                to_agent="orchestrator",
                message_type="critique_response",
                summary=f"{self.agent_name} responded to critique: {response.decision}",
                payload=response.model_dump(),
                decision_rationale=response.rationale,
            )

        state["critique_responses"] = responses
        return state
