"""Crucible Logic Analysis Tools.

Author: Anum Agarwal (anum777)
Role: Logic Reviewer Specialist
Module: tools/logic_tools.py
"""

from __future__ import annotations

import ast
from typing import Any


def analyze_ast(code: str) -> dict[str, Any]:
    """Parse Python source code into an AST and extract structural metrics.

    Identifies functions, classes, arguments, maximum nesting depth,
    and potential unreachable code blocks.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {
            "valid": False,
            "error": f"SyntaxError at line {e.lineno}: {e.msg}",
            "line": e.lineno or 1,
            "functions": [],
            "classes": [],
            "max_nesting_depth": 0,
            "unreachable_blocks": [],
        }

    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    unreachable_blocks: list[dict[str, Any]] = []

    class StructureVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.current_depth = 0
            self.max_depth = 0

        def _track_depth(self, node: ast.AST) -> None:
            self.current_depth += 1
            if self.current_depth > self.max_depth:
                self.max_depth = self.current_depth
            self.generic_visit(node)
            self.current_depth -= 1

        def visit_If(self, node: ast.If) -> None:
            self._check_unreachable(node.body)
            self._check_unreachable(node.orelse)
            self._track_depth(node)

        def visit_For(self, node: ast.For) -> None:
            self._check_unreachable(node.body)
            self._track_depth(node)

        def visit_While(self, node: ast.While) -> None:
            self._check_unreachable(node.body)
            self._track_depth(node)

        def visit_Try(self, node: ast.Try) -> None:
            self._check_unreachable(node.body)
            self._track_depth(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            docstring = ast.get_docstring(node)
            functions.append({
                "name": node.name,
                "line_start": node.lineno,
                "line_end": getattr(node, "end_lineno", node.lineno),
                "args": [arg.arg for arg in node.args.args],
                "has_docstring": docstring is not None,
            })
            self._check_unreachable(node.body)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            docstring = ast.get_docstring(node)
            functions.append({
                "name": node.name,
                "line_start": node.lineno,
                "line_end": getattr(node, "end_lineno", node.lineno),
                "args": [arg.arg for arg in node.args.args],
                "has_docstring": docstring is not None,
            })
            self._check_unreachable(node.body)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            classes.append({
                "name": node.name,
                "line_start": node.lineno,
                "line_end": getattr(node, "end_lineno", node.lineno),
            })
            self.generic_visit(node)

        def _check_unreachable(self, stmts: list[ast.stmt]) -> None:
            for idx, stmt in enumerate(stmts):
                if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                    if idx + 1 < len(stmts):
                        dead_stmt = stmts[idx + 1]
                        unreachable_blocks.append({
                            "terminator_line": stmt.lineno,
                            "unreachable_line_start": dead_stmt.lineno,
                            "unreachable_line_end": getattr(dead_stmt, "end_lineno", dead_stmt.lineno),
                        })

    visitor = StructureVisitor()
    visitor.visit(tree)

    return {
        "valid": True,
        "functions": functions,
        "classes": classes,
        "max_nesting_depth": visitor.max_depth,
        "unreachable_blocks": unreachable_blocks,
    }


def compute_complexity(code: str) -> dict[str, Any]:
    """Calculate cyclomatic complexity metrics for all functions using radon."""
    try:
        from radon.complexity import cc_rank, cc_visit

        blocks = cc_visit(code)
        results: list[dict[str, Any]] = []
        for block in blocks:
            results.append({
                "name": block.name,
                "line_start": block.lineno,
                "complexity": block.complexity,
                "rank": cc_rank(block.complexity),
            })
        return {"success": True, "blocks": results}
    except Exception as e:
        return {"success": False, "error": f"Radon analysis failed: {e}", "blocks": []}
