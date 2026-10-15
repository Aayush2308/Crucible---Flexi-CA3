# Crucible — Multi-Agent Automated Code Review & Arbitration System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/api-FastAPI-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Crucible** is a production-grade multi-agent code analysis and review engine. Rather than relying on a single generalist LLM prompt that compromises between competing concerns, Crucible employs three specialised worker agents with opposing objective functions (correctness, safety, readability) coordinated by an autonomous LLM Orchestrator that detects disagreements, coordinates peer critiques, and issues binding arbitration rulings.

---

## 🏛️ System Architecture

Crucible follows the **Orchestrator-Worker with Shared Blackboard and Peer-Critique Channel** pattern built on top of **LangGraph**:

```
                              ┌────────────────┐
                              │  User / Client │
                              └───────┬────────┘
                                      │ ReviewRequest
                                      ▼
                         ┌─────────────────────────┐
                         │   FastAPI Server (SSE)  │
                         └────────────┬────────────┘
                                      │ StateGraph
                                      ▼
                         ┌─────────────────────────┐
                         │      Orchestrator       │
                         │   (Gemini 2.0 Flash)    │
                         └───────┬─────────┬───────┘
                                 │         │
                 ┌───────────────┘         └───────────────┐
                 │ Triage Plan                     │ Triage Plan
                 ▼                                 ▼
      ┌────────────────────┐            ┌────────────────────┐
      │   Logic Reviewer   │            │  Security Auditor  │
      │ (Gemini 1.5 Flash) │            │ (Gemini 1.5 Flash) │
      └─────────┬──────────┘            └──────────┬─────────┘
                │ Findings                         │ Findings
                └────────────────┬─────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │    Shared Blackboard    │
                    │     (CrucibleState)     │
                    └────────────┬────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
                 ▼                               ▼
      ┌────────────────────┐            ┌────────────────────┐
      │  Style & Doc Agent │            │    Trace Logger    │
      │ (Gemini 1.5 Flash) │            │ (Structured JSON)  │
      └────────────────────┘            └────────────────────┘
```

### The Specialist Agents

| Agent | Canonical Class | Model | Primary Objective | Deterministic Tools |
|---|---|---|---|---|
| **Logic Reviewer** | `LogicReviewer` | `gemini-1.5-flash` | Algorithmic correctness & edge cases | Python `ast` parser, `radon` complexity scorer |
| **Security Auditor** | `SecurityAuditor` | `gemini-1.5-flash` | CWE vulnerabilities & secret exposure | `bandit` SAST scanner, regex secret detector |
| **Style & Doc Agent** | `StyleDocAgent` | `gemini-1.5-flash` | PEP 8 conformity & docstring quality | `pycodestyle`, `pydocstyle` |
| **Orchestrator** | `Orchestrator` | `gemini-2.0-flash` | Triage, conflict detection & arbitration | Dynamic routing, critique channel, synthesis |

---

## 📂 Repository Structure

```
Crucible---Flexi-CA3/
├── .github/
│   └── pull_request_template.md    # Standardised PR review template
├── agents/                         # Agent definitions inheriting BaseAgent
│   ├── __init__.py
│   ├── base.py                     # BaseAgent abstract base class
│   ├── orchestrator.py             # Orchestrator & LangGraph state machine
│   ├── logic_reviewer.py           # Logic Reviewer agent
│   ├── security_auditor.py         # Security Auditor agent
│   └── style_doc_agent.py          # Style & Documentation agent
├── tools/                          # Static analysis tool wrappers
│   ├── __init__.py
│   ├── tool_base.py                # run_tool wrapper with fault injection
│   ├── logic_tools.py              # AST and Radon complexity analyzers
│   ├── security_tools.py           # Bandit and secret detection scanners
│   └── style_tools.py              # Pycodestyle and Pydocstyle checkers
├── lib/                            # Core shared infrastructure
│   ├── __init__.py
│   ├── schemas.py                  # Single source of truth for Pydantic models
│   ├── blackboard.py               # CrucibleState TypedDict & state factory
│   ├── trace_logger.py             # Execution trace recording & disk flush
│   └── llm_provider.py             # Unified Gemini client with mock fallback
├── api/                            # Web API & SSE streaming
│   ├── __init__.py
│   └── main.py                     # FastAPI application
├── ui/                             # Static frontend served by FastAPI
│   ├── index.html                  # Dashboard layout
│   ├── style.css                   # Glassmorphic dark UI styling
│   └── app.js                      # SSE stream consumer & timeline renderer
├── tests/                          # Automated unit & integration tests
│   ├── __init__.py
│   ├── conftest.py                 # Fixtures & offline mock LLM provider
│   ├── test_orchestrator.py
│   ├── test_logic_reviewer.py
│   ├── test_security_auditor.py
│   └── test_style_doc_agent.py
├── docs/                           # Project documentation
│   ├── synopsis.md                 # Project Synopsis
│   └── design_document.md          # Comprehensive System Design Document
├── traces/                         # Execution traces generated from real runs
│   └── .gitkeep
├── scripts/                        # Automation & verification scripts
│   ├── export_trace.py             # Mechanical trace export with head-tail truncation
│   └── warmup.py                   # Render deployment keep-alive ping
├── .env.example                    # Template for environment variables
├── .gitignore                      # Git exclusion rules
├── requirements.txt                # Pinned dependencies
└── conftest.py                     # Root test discovery configuration
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.11 or higher
- Git

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Aayush2308/Crucible---Flexi-CA3.git
cd Crucible---Flexi-CA3

# Create and activate a virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Setup
```bash
# Copy example environment configuration
cp .env.example .env

# Edit .env and insert your Gemini API Key
# GEMINI_API_KEY=your_key_here
```

### 4. Running the Application
```bash
# Start the FastAPI server with live reload
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```
Open [http://localhost:8000](http://localhost:8000) in your web browser to access the interactive review dashboard.

---

## 🧪 Running the Test Suite

Crucible provides comprehensive automated tests exercising individual agents, tool wrappers, fault-injection fallbacks, and multi-agent coordination. All tests utilize the mock LLM provider by default to execute deterministically without consuming API quotas:

```bash
# Run all unit tests with short traceback
pytest -v --tb=short
```

---

## 👥 Team & Ownership

| Team Member | GitHub Username | Role & Assigned Components |
|---|---|---|
| **Aayush Joshi** (Lead) | `Aayush2308` | Orchestrator, Shared Core, API & Coordination Graph |
| **Anum Agarwal** | `anum777` | Logic Reviewer Agent, AST/Radon Tools & Design Document |
| **Anushka Desai** | `anushkadesai13` | Security Auditor Agent, SAST/Secrets Tools & Trace Exporter |
| **Arya Shah** | `Arya-A-Shah` | Style & Doc Agent, Frontend Dashboard & Cloud Deployment |

---

## 📜 License
Distributed under the MIT License. See `LICENSE` for more information.
