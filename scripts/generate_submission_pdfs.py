"""Generate clean, publication-quality PDFs for Faculty Submission.

Generates:
1. Crucible_Project_Synopsis.pdf (from docs/synopsis.md)
2. Crucible_Design_Document.pdf (from docs/design_document.md)
"""

import os
from pathlib import Path
import pymupdf  # PyMuPDF / fitz

DOCS_DIR = Path("docs")

def build_synopsis_pdf():
    pdf_path = DOCS_DIR / "Crucible_Project_Synopsis.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4 size

    # Colors
    c_primary = (0.08, 0.22, 0.45)   # Navy
    c_accent  = (0.85, 0.35, 0.15)   # Orange
    c_dark    = (0.15, 0.15, 0.15)   # Charcoal
    c_muted   = (0.45, 0.45, 0.45)   # Gray
    c_bg      = (0.96, 0.97, 0.99)   # Light blue tint

    # Top banner background
    rect_banner = pymupdf.Rect(0, 0, 595, 110)
    page.draw_rect(rect_banner, color=c_primary, fill=c_primary)

    # Header text
    page.insert_text((40, 48), "CRUCIBLE", fontname="helv", fontsize=24, color=(1, 1, 1))
    page.insert_text((40, 72), "Autonomous Multi-Agent Code Review & Arbitration Studio", fontname="helv", fontsize=12, color=(0.9, 0.9, 0.9))
    page.insert_text((40, 92), "Course: Flexi-CA3 / Multi-Agent Systems | Submission: Project Synopsis", fontname="helv", fontsize=10, color=(0.8, 0.8, 0.8))

    y = 145

    def add_section(title, text):
        nonlocal y
        # Section Header Pill
        page.draw_rect(pymupdf.Rect(40, y - 14, 555, y + 8), color=c_bg, fill=c_bg)
        page.draw_line((40, y + 8), (555, y + 8), color=c_accent, width=1.5)
        page.insert_text((46, y), title.upper(), fontname="helv", fontsize=12, color=c_primary)
        y += 26

        # Paragraph text wrapped
        rect = pymupdf.Rect(40, y, 555, y + 300)
        rc = page.insert_textbox(rect, text, fontname="helv", fontsize=10, color=c_dark, lineheight=1.4)
        # Approximate height consumed
        # Calculate lines by counting length
        words = len(text.split())
        approx_lines = words / 12
        y += int(approx_lines * 14) + 24

    add_section(
        "1. Problem Statement",
        "Software developers—particularly students, bootcamp graduates, and junior engineers—routinely receive "
        "code feedback that is either too narrow (a linter catching only style issues) or too shallow (a single AI prompt "
        "giving generic critiques). A single AI model tasked with reviewing code faces a fundamental trade-off: it can "
        "assess logical correctness, or security vulnerabilities, or documentation quality, but attempting all three "
        "simultaneously spreads its attention budget so thin that each perspective becomes superficial. Furthermore, traditional "
        "linters operate in isolation, lacking contextual understanding, multi-turn critique, or autonomous remediation."
    )

    add_section(
        "2. Solution & Multi-Agent Architecture",
        "Crucible is an autonomous multi-agent code evaluation system where four specialized agents collaborate, disagree, "
        "and critique each other across a shared blackboard to produce a comprehensive, multi-perspective code review:\n\n"
        "• Logic Reviewer: Evaluates algorithmic correctness, off-by-one errors, and control flow using AST analysis & Radon cyclomatic complexity.\n"
        "• Security Auditor: Scans for injection vulnerabilities (CWE-89 SQLi), token leakage (CWE-798), and unsafe APIs using Bandit SAST and pattern detection.\n"
        "• Style & Doc Agent: Analyzes idiomatic formatting (PEP 8, ESLint, gofmt) and documentation completeness (PEP 257, JSDoc, Go doc).\n"
        "• Orchestrator: Built on LangGraph, dynamically routes reviews, detects cross-agent conflicts, arbitrates disagreements with written rationales, and synthesizes a final severity-ranked report.\n\n"
        "Crucible incorporates autonomous fault-injection fallback (Category C2) and an autonomous Auto-Fix & Refactor engine that remediates detected flaws into secure, production-ready code."
    )

    add_section(
        "3. Target User & Project Scope",
        "Crucible is designed for students learning software engineering, bootcamp developers preparing for technical interviews, "
        "and development teams seeking automated, high-assurance multi-perspective code auditing. The system accepts source code "
        "in multiple languages (Python, JavaScript, Go), optional runtime context, and provides a real-time reactive blackboard "
        "timeline, audit event logs, automated security patch application, and comprehensive compliance artifacts."
    )

    # Footer
    page.draw_line((40, 805), (555, 805), color=c_muted, width=0.5)
    page.insert_text((40, 820), "Team Crucible: Aayush Joshi, Anum Agarwal, Anushka Desai, Arya Shah", fontname="helv", fontsize=8, color=c_muted)
    page.insert_text((480, 820), "Page 1 of 1", fontname="helv", fontsize=8, color=c_muted)

    doc.save(str(pdf_path))
    doc.close()
    print(f"Generated: {pdf_path}")


def build_design_doc_pdf():
    pdf_path = DOCS_DIR / "Crucible_Design_Document.pdf"
    doc = pymupdf.open()
    
    # Colors
    c_primary = (0.08, 0.22, 0.45)   # Navy
    c_accent  = (0.85, 0.35, 0.15)   # Orange
    c_dark    = (0.15, 0.15, 0.15)   # Charcoal
    c_muted   = (0.45, 0.45, 0.45)   # Gray
    c_bg      = (0.96, 0.97, 0.99)   # Light blue tint

    # PAGE 1: Architecture & Agent Roles
    page1 = doc.new_page(width=595, height=842)
    page1.draw_rect(pymupdf.Rect(0, 0, 595, 105), color=c_primary, fill=c_primary)
    page1.insert_text((40, 45), "CRUCIBLE — SYSTEM DESIGN DOCUMENT", fontname="helv", fontsize=20, color=(1, 1, 1))
    page1.insert_text((40, 68), "Multi-Agent Code Review & Autonomous Arbitration Architecture", fontname="helv", fontsize=11, color=(0.9, 0.9, 0.9))
    page1.insert_text((40, 88), "Course: Flexi-CA3 | Orchestrator-Worker with Blackboard Pattern", fontname="helv", fontsize=9, color=(0.8, 0.8, 0.8))

    y = 130
    def add_header(page, title):
        nonlocal y
        page.draw_rect(pymupdf.Rect(40, y - 12, 555, y + 8), color=c_bg, fill=c_bg)
        page.draw_line((40, y + 8), (555, y + 8), color=c_accent, width=1.5)
        page.insert_text((46, y), title.upper(), fontname="helv", fontsize=11, color=c_primary)
        y += 24

    add_header(page1, "1. Architecture Overview & Communication Pattern")
    rect = pymupdf.Rect(40, y, 555, y + 100)
    text1 = (
        "Crucible implements a hybrid Blackboard + Dynamic Peer-Critique + Hierarchical Arbitration multi-agent topology "
        "orchestrated using LangGraph state machines. All agent interactions occur asynchronously through an append-only "
        "shared blackboard state (CrucibleState) rather than point-to-point hardcoded calls. When specialists produce conflicting "
        "findings (e.g. Logic Reviewer grading code correct while Security Auditor flags an unvalidated SQL query), the Orchestrator "
        "initiates a targeted critique round. If consensus remains unreached, the Orchestrator executes binding LLM arbitration "
        "with explicit written rationales."
    )
    page1.insert_textbox(rect, text1, fontname="helv", fontsize=9.5, color=c_dark, lineheight=1.35)
    y += 90

    add_header(page1, "2. Agent Specifications & Specialist Tools")
    
    # Table header
    headers = [("Agent", 110), ("LLM Engine", 90), ("Static Tools", 140), ("Core Responsibility", 175)]
    tx = 40
    page1.draw_rect(pymupdf.Rect(40, y - 10, 555, y + 12), color=c_primary, fill=c_primary)
    for h, w in headers:
        page1.insert_text((tx + 4, y + 5), h, fontname="helv", fontsize=9, color=(1, 1, 1))
        tx += w
    y += 18

    # Table rows
    rows = [
        ("Orchestrator", "Gemini 3.5 Flash", "LangGraph, Blackboard", "Triage, worker dispatch, conflict detection, binding arbitration & synthesis."),
        ("Logic Reviewer", "Gemini 3.5 Flash", "AST Parser, Radon CC", "Algorithmic correctness, off-by-one errors, edge cases, cyclomatic complexity."),
        ("Security Auditor", "Gemini 3.5 Flash", "Bandit SAST, Secret Scanner", "SQL injection (CWE-89), hardcoded secrets (CWE-798), CVE/CWE tagging."),
        ("Style & Doc Agent", "Gemini 3.5 Flash", "pycodestyle, pydocstyle", "PEP 8/ESLint formatting, naming conventions, docstring completeness (PEP 257).")
    ]
    for agent, model, tools, resp in rows:
        page1.draw_rect(pymupdf.Rect(40, y - 6, 555, y + 26), color=(0.9, 0.9, 0.9), fill=(1, 1, 1) if rows.index((agent, model, tools, resp)) % 2 == 0 else c_bg)
        page1.insert_text((44, y + 8), agent, fontname="helv", fontsize=8.5, color=c_primary)
        page1.insert_text((154, y + 8), model, fontname="helv", fontsize=8, color=c_dark)
        page1.insert_text((244, y + 8), tools, fontname="helv", fontsize=8, color=c_dark)
        page1.insert_textbox(pymupdf.Rect(384, y - 4, 550, y + 24), resp, fontname="helv", fontsize=7.5, color=c_dark)
        y += 32

    y += 10
    add_header(page1, "3. Autonomous Routing & State Convergence")
    text2 = (
        "Crucible replaces rigid sequential execution with dynamic LLM-driven dispatching:\n"
        "• Non-Hardcoded Routing: The Orchestrator inspects incoming code characteristics and selects which specialist agents "
        "to run and what specific focus areas to assign.\n"
        "• Termination Safeguard: A hard limit (budget_rounds = 3) prevents runaway cycles, ensuring guaranteed convergence.\n"
        "• Traceability: Every state transition emits an immutable TraceEvent payload with timestamps and decision rationales."
    )
    page1.insert_textbox(pymupdf.Rect(40, y, 555, y + 100), text2, fontname="helv", fontsize=9.5, color=c_dark, lineheight=1.35)

    page1.draw_line((40, 805), (555, 805), color=c_muted, width=0.5)
    page1.insert_text((40, 820), "Crucible Architecture & Design Document | Team Crucible", fontname="helv", fontsize=8, color=c_muted)
    page1.insert_text((480, 820), "Page 1 of 2", fontname="helv", fontsize=8, color=c_muted)

    # PAGE 2: Fault Tolerance, Technology Stack & Deployment
    page2 = doc.new_page(width=595, height=842)
    page2.draw_rect(pymupdf.Rect(0, 0, 595, 60), color=c_primary, fill=c_primary)
    page2.insert_text((40, 38), "CRUCIBLE — SYSTEM DESIGN DOCUMENT (PAGE 2)", fontname="helv", fontsize=14, color=(1, 1, 1))

    y = 85
    add_header(page2, "4. Robustness & Fault Tolerance (Category C2 Compliance)")
    text3 = (
        "Crucible incorporates an isolated tool execution harness (tools/tool_base.py) with exception containment:\n"
        "• Simulated Fault Injection: If a static tool fails (e.g. Bandit crashing in Scenario D), Crucible catches the failure without "
        "crashing the pipeline.\n"
        "• Autonomous Re-Planning: The affected agent immediately emits a 'fallback' trace event and seamlessly transitions to pure LLM "
        "deep-reasoning to complete the review.\n"
        "• Language Agility: When reviewing non-Python code (JavaScript, Go), static tools automatically record a fallback and the LLM "
        "agents autonomously evaluate language-specific vulnerabilities, complexity, and idiomatic conventions."
    )
    page2.insert_textbox(pymupdf.Rect(40, y, 555, y + 120), text3, fontname="helv", fontsize=9.5, color=c_dark, lineheight=1.35)
    y += 115

    add_header(page2, "5. Technology Stack")
    tech_items = [
        ("Multi-Agent Framework", "LangGraph 1.2+ (StateGraph, StateMachine, MemorySaver)"),
        ("LLM Foundation", "Google Gemini 3.5 Flash via google-generativeai SDK"),
        ("Web API Server", "FastAPI (Python 3.11), Uvicorn ASGI, Server-Sent Events (SSE)"),
        ("Static Analysis Suite", "Bandit (SAST), Radon (Cyclomatic Complexity), pycodestyle, pydocstyle"),
        ("Client Dashboard", "Responsive Single Page Architecture, CSS Glassmorphism, Vanilla JS SSE client"),
        ("Containerization & Cloud", "Docker (python:3.11-slim) & Render.com automated PaaS deployment")
    ]
    for cat, val in tech_items:
        page2.insert_text((44, y + 10), f"• {cat}:", fontname="helv", fontsize=9, color=c_primary)
        page2.insert_text((190, y + 10), val, fontname="helv", fontsize=9, color=c_dark)
        y += 18

    y += 15
    add_header(page2, "6. Auto-Fix Remediation & Deployment")
    text4 = (
        "In addition to detection, Crucible provides autonomous patch remediation (/autofix endpoint). Detected vulnerabilities "
        "(such as raw SQL string concatenation CWE-89) are patched using parameterized queries and prepared statements, while "
        "cyclomatic complexity is flattened into clean, modular helper structures. The web application is fully containerized "
        "using a production Dockerfile and deployed on Render.com with continuous health probe monitoring (/health)."
    )
    page2.insert_textbox(pymupdf.Rect(40, y, 555, y + 100), text4, fontname="helv", fontsize=9.5, color=c_dark, lineheight=1.35)

    page2.draw_line((40, 805), (555, 805), color=c_muted, width=0.5)
    page2.insert_text((40, 820), "Crucible Architecture & Design Document | Team Crucible", fontname="helv", fontsize=8, color=c_muted)
    page2.insert_text((480, 820), "Page 2 of 2", fontname="helv", fontsize=8, color=c_muted)

    doc.save(str(pdf_path))
    doc.close()
    print(f"Generated: {pdf_path}")

if __name__ == "__main__":
    build_synopsis_pdf()
    build_design_doc_pdf()
