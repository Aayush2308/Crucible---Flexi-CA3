"""Crucible Security Analysis Tools.

Author: Anushka Desai (anushkadesai13)
Role: Security Auditor Specialist
Module: tools/security_tools.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from typing import Any


def scan_bandit(code: str) -> dict[str, Any]:
    """Execute Bandit SAST static vulnerability scanner against Python source code."""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        cmd = ["bandit", "-r", tmp_path, "-f", "json", "-q"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        raw_output = proc.stdout.strip()
        data = json.loads(raw_output) if raw_output else {}

        raw_results = data.get("results", [])
        issues: list[dict[str, Any]] = []

        for item in raw_results:
            cwe_info = item.get("issue_cwe", {})
            cwe_id = f"CWE-{cwe_info.get('id')}" if isinstance(cwe_info, dict) and "id" in cwe_info else None

            issues.append({
                "test_id": item.get("test_id"),
                "cwe_id": cwe_id,
                "line_number": item.get("line_number"),
                "line_range": item.get("line_range", []),
                "issue_text": item.get("issue_text"),
                "severity": item.get("issue_severity", "MEDIUM").lower(),
                "confidence": item.get("issue_confidence", "MEDIUM").lower(),
                "code_snippet": item.get("code", "").strip(),
            })

        return {
            "success": True,
            "issues_count": len(issues),
            "issues": issues,
            "metrics": data.get("metrics", {}),
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Bandit execution failed: {e}",
            "issues_count": 0,
            "issues": [],
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def detect_secrets(code: str) -> dict[str, Any]:
    """Scan source code for high-entropy tokens, hardcoded credentials, and private keys."""
    patterns = {
        "aws_access_key": re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
        "jwt_token": re.compile(r"\b(eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+)\b"),
        "generic_secret": re.compile(
            r"""(?i)(?:api_key|apikey|secret|token|password|passwd|auth_token)[\s:=]+["']([a-zA-Z0-9_\-\.]{12,})["']"""
        ),
        "private_key_header": re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
    }

    findings: list[dict[str, Any]] = []
    lines = code.splitlines()

    for line_idx, line in enumerate(lines, start=1):
        for pattern_name, pattern in patterns.items():
            matches = pattern.finditer(line)
            for match in matches:
                matched_val = match.group(0)
                # Mask secret value to prevent credential leaking in traces
                masked = (
                    matched_val[:4] + "*" * (len(matched_val) - 8) + matched_val[-4:]
                    if len(matched_val) > 8
                    else "********"
                )
                findings.append({
                    "line": line_idx,
                    "pattern": pattern_name,
                    "masked_preview": masked,
                    "cwe_id": "CWE-798",
                })

    return {
        "success": True,
        "secrets_found": len(findings),
        "findings": findings,
    }
