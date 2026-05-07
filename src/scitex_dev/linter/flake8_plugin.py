"""Flake8 plugin for SciTeX linter.

Usage:
    pip install scitex-linter
    flake8 --select STX script.py
"""

import ast

from .checker import SciTeXChecker


class SciTeXFlake8Checker:
    """Flake8 checker wrapping the SciTeX AST visitor."""

    name = "scitex-linter"
    version = "0.1.0"

    def __init__(self, tree: ast.AST, filename: str = "<stdin>", lines: list = None):
        self._tree = tree
        self._filename = filename
        self._lines = lines or []

    def run(self):
        """Yield (line, col, message, type) tuples for flake8."""
        source_lines = [line.rstrip("\n") for line in self._lines]
        checker = SciTeXChecker(source_lines, filepath=self._filename)
        checker.visit(self._tree)

        for issue in checker.get_issues():
            # flake8 format: (line, col, "CODE message", type)
            code = issue.rule.id.replace("-", "")  # STX-S001 -> STXS001
            msg = f"{code} {issue.rule.message}"
            yield (issue.line, issue.col, msg, type(self))
