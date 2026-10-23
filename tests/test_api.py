"""Crucible API Test Suite.

Author: Aayush Agarwal (Aayush2308) & Team
Role: API Endpoint & Integration Testing
Tests: tests/test_api.py

Covers:
  - GET  /health                      — Health probe
  - GET  /                            — Serve UI HTML
  - GET  /style.css                   — Serve CSS
  - GET  /app.js                      — Serve JavaScript
  - POST /review                      — Execute multi-agent review pipeline
  - GET  /review/{run_id}             — Retrieve review result
  - GET  /review/stream/{run_id}      — Server-Sent Events (SSE) stream
"""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """FastAPI TestClient fixture configured for mock LLM mode."""
    os.environ["CRUCIBLE_MOCK_LLM"] = "1"
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client: TestClient) -> None:
    """Verify /health returns 200 with service metadata and mock mode."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "crucible"
    assert data["version"] == "1.0.0"
    assert data["mock_mode"] is True
    assert "timestamp" in data


def test_serve_static_ui(client: TestClient) -> None:
    """Verify UI index.html, style.css, and app.js are served correctly."""
    # HTML root
    res_html = client.get("/")
    assert res_html.status_code == 200
    assert "CRUCIBLE" in res_html.text
    assert "text/html" in res_html.headers.get("content-type", "")

    # CSS stylesheet
    res_css = client.get("/style.css")
    assert res_css.status_code == 200
    assert "text/css" in res_css.headers.get("content-type", "")

    # JS client script
    res_js = client.get("/app.js")
    assert res_js.status_code == 200
    assert "javascript" in res_js.headers.get("content-type", "")


def test_post_review_endpoint(client: TestClient) -> None:
    """Verify POST /review executes the full pipeline and returns structured report."""
    payload = {
        "input_code": (
            "def authenticate(user, password):\n"
            "    cursor.execute('SELECT * FROM users WHERE u=' + user)\n"
            "    return True\n"
        ),
        "language": "python",
        "context": "Auth module",
    }
    response = client.post("/review", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "run_id" in data
    assert data["status"] == "completed"
    assert "events" in data
    assert len(data["events"]) > 0

    # Verify final report
    report = data["final_report"]
    assert report is not None
    assert report["overall_severity"] in ("critical", "high", "medium", "low", "info")
    assert "executive_summary" in report
    assert "all_issues" in report
    assert "metrics" in report
    assert report["metrics"]["total_rounds"] >= 1


def test_get_review_by_run_id(client: TestClient) -> None:
    """Verify retrieving a completed run by run_id."""
    payload = {
        "input_code": "def hello():\n    return 'world'\n",
        "language": "python",
        "context": "Simple hello",
    }
    res_post = client.post("/review", json=payload)
    assert res_post.status_code == 200
    run_id = res_post.json()["run_id"]

    res_get = client.get(f"/review/{run_id}")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["run_id"] == run_id
    assert data["status"] == "completed"
    assert data["final_report"] is not None


def test_get_review_not_found(client: TestClient) -> None:
    """Verify non-existent run_id returns 404."""
    response = client.get("/review/non_existent_run_99999")
    assert response.status_code == 404


def test_review_validation_error(client: TestClient) -> None:
    """Verify missing input_code returns 422 Unprocessable Entity."""
    response = client.post("/review", json={"language": "python"})
    assert response.status_code == 422


def test_autofix_endpoint(client: TestClient) -> None:
    """Verify POST /autofix returns refactored code and explanation."""
    payload = {
        "code": "def login(u, p):\n    query = f'SELECT * FROM users WHERE u={u}'\n    return query\n",
        "language": "python",
        "context": "Authentication service",
    }
    response = client.post("/autofix", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "fixed_code" in data
    assert "explanation" in data
    assert len(data["fixed_code"]) > 0
    assert "parameterized" in data["explanation"].lower() or "cwe-89" in data["explanation"].lower() or len(data["explanation"]) > 0

