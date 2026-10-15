"""Crucible Pytest Test Fixtures and Mock Providers.

Provides offline mock LLM generators, sample code snippets for demo scenarios A-D,
and fault-injection context managers for Category C2 robustness validation.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator
import pytest

from lib.blackboard import CrucibleState, make_initial_state
from lib.schemas import ReviewRequest


@pytest.fixture(autouse=True)
def ensure_mock_mode() -> Generator[None, None, None]:
    """Force CRUCIBLE_MOCK_LLM=1 for all automated tests to guarantee zero external API calls."""
    orig = os.environ.get("CRUCIBLE_MOCK_LLM")
    os.environ["CRUCIBLE_MOCK_LLM"] = "1"
    try:
        yield
    finally:
        if orig is None:
            os.environ.pop("CRUCIBLE_MOCK_LLM", None)
        else:
            os.environ["CRUCIBLE_MOCK_LLM"] = orig


@pytest.fixture
def fault_env() -> Generator[None, None, None]:
    """Context manager or helper fixture for setting CRUCIBLE_FAULT."""
    @contextmanager
    def _set_fault(tool_name: str) -> Generator[None, None, None]:
        orig = os.environ.get("CRUCIBLE_FAULT")
        os.environ["CRUCIBLE_FAULT"] = tool_name
        try:
            yield
        finally:
            if orig is None:
                os.environ.pop("CRUCIBLE_FAULT", None)
            else:
                os.environ["CRUCIBLE_FAULT"] = orig

    return _set_fault  # type: ignore


@pytest.fixture
def sample_code_scenario_a() -> str:
    """Demo Scenario A: Code featuring SQL injection and high cyclomatic complexity."""
    return '''def login(username, password):
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    result = db.execute(query)
    user = result.fetchone()
    if user:
        return {"token": generate_token(user.id), "status": "success"}
    return {"status": "failure"}

def calculate_discount(items, customer_type):
    total = 0
    for item in items:
        if customer_type == "premium":
            for sub in item.sub_items:
                for detail in sub.details:
                    total += detail.price * 0.8
        elif customer_type == "regular":
            total += item.price * 0.9
    return total
'''


@pytest.fixture
def sample_code_scenario_b() -> str:
    """Demo Scenario B: Clean, well-formatted Python function."""
    return '''"""Utility module providing math operations."""

def add_positive_numbers(a: int, b: int) -> int:
    """Calculate the sum of two positive integers."""
    if a < 0 or b < 0:
        raise ValueError("Both numbers must be non-negative.")
    return a + b
'''


@pytest.fixture
def sample_code_scenario_c() -> str:
    """Demo Scenario C: Non-code text for input validation testing."""
    return "This is plain prose, not valid Python code, describing a system requirement."


@pytest.fixture
def sample_code_secrets() -> str:
    """Code snippet containing hardcoded credentials for secret detection testing."""
    return '''import requests

AWS_SECRET_KEY = "AKIAIOSFODNN7EXAMPLE"
API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ae7H8M7ObGd2aG8jHrOcfJw"

def fetch_data():
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    return requests.get("https://api.example.com/data", headers=headers)
'''


@pytest.fixture
def initial_state(sample_code_scenario_a: str) -> CrucibleState:
    """Provide a clean CrucibleState initialized with Scenario A."""
    req = ReviewRequest(
        input_code=sample_code_scenario_a,
        language="python",
        context="E-commerce authentication and discount calculation module.",
    )
    return make_initial_state(req)
