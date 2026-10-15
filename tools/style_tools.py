"""Crucible Code Style and Documentation Analysis Tools.

Author: Arya Shah (Arya-A-Shah)
Role: Style & Doc Specialist
Module: tools/style_tools.py
"""

from __future__ import annotations

import os
import tempfile
from typing import Any
import pycodestyle
import pydocstyle


def check_pycodestyle(code: str) -> dict[str, Any]:
    """Execute pycodestyle (PEP 8) linter against Python source code."""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        class MemoryReport(pycodestyle.BaseReport):
            def __init__(self, options):
                super().__init__(options)
                self.violations: list[dict[str, Any]] = []

            def error(self, line_number, offset, text, check):
                code_rule = super().error(line_number, offset, text, check)
                if code_rule:
                    self.violations.append({
                        "line": line_number,
                        "column": offset + 1,
                        "rule": code_rule,
                        "message": text,
                    })
                return code_rule

        style_guide = pycodestyle.StyleGuide(reporter=MemoryReport, quiet=True)
        report = style_guide.check_files([tmp_path])
        violations = getattr(report, "violations", [])

        return {
            "success": True,
            "violations_count": len(violations),
            "violations": violations[:20],  # cap to top 20 to avoid token bloat
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"pycodestyle execution failed: {e}",
            "violations_count": 0,
            "violations": [],
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def check_pydocstyle(code: str) -> dict[str, Any]:
    """Execute pydocstyle (PEP 257) docstring compliance analyzer."""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        issues: list[dict[str, Any]] = []
        for err in pydocstyle.check([tmp_path]):
            issues.append({
                "line": err.line,
                "rule": err.code,
                "message": err.short_desc,
                "context": err.context,
            })

        return {
            "success": True,
            "issues_count": len(issues),
            "issues": issues[:20],
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"pydocstyle execution failed: {e}",
            "issues_count": 0,
            "issues": [],
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
