#!/usr/bin/env python3
"""Lint MCP tools for scitex-linter."""

import ast

from pathlib import Path
from typing import Optional


def register_lint_tools(mcp) -> None:
    """Register lint-related MCP tools."""

    @mcp.tool()
    def linter_check(
        path: str, severity: str = "info", category: Optional[str] = None
    ) -> dict:
        """Lint one existing regular file using enabled installed SciTeX checks.

        Python, notebook, Markdown and reST inputs use the owning filetype
        dispatcher. Missing or non-file targets fail; directories are not
        traversed. Source is analyzed, never executed. Filter reported issues
        by minimum severity (error/warning/info) and comma-separated category
        names from the actual catalog. Findings do not prove all optional
        providers ran, and this endpoint is not a Python syntax validator."""
        from ...checker import lint_file
        from ...config import load_config
        from ...formatter import to_json
        from ...rules import SEVERITY_ORDER

        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"Lint target does not exist: {path}")
        if not target.is_file():
            raise ValueError(f"Lint target must be a regular file: {path}")

        config = load_config(path)
        issues = lint_file(path, config=config)
        min_sev = SEVERITY_ORDER.get(severity, 0)
        categories = set(category.split(",")) if category else None

        issues = [
            i
            for i in issues
            if SEVERITY_ORDER[i.rule.severity] >= min_sev
            and (categories is None or i.rule.category in categories)
        ]

        return to_json(issues, path)

    @mcp.tool()
    def linter_list_rules(
        category: Optional[str] = None, severity: Optional[str] = None
    ) -> dict:
        """List the installed SciTeX lint catalog, including provider rules.

        Return each rule's ID, category, severity, message and suggested fix,
        plus the filtered count. The catalog size depends on this interpreter's
        installed providers declared through `scitex_dev.linter.plugins`.
        Category filters match comma-separated exact
        catalog strings; severity is an exact match. Catalog presence and
        counts do not establish that a rule ran for a particular file."""
        from ... import list_rules

        rules_list = list_rules()

        if category:
            cats = set(category.split(","))
            rules_list = [r for r in rules_list if r.category in cats]
        if severity:
            rules_list = [r for r in rules_list if r.severity == severity]

        return {
            "rules": [
                {
                    "id": r.id,
                    "severity": r.severity,
                    "category": r.category,
                    "message": r.message,
                    "suggestion": r.suggestion,
                }
                for r in rules_list
            ],
            "count": len(rules_list),
        }

    @mcp.tool()
    def linter_check_source(source: str, filepath: str = "<stdin>") -> dict:
        """Analyze a Python source string without executing or saving it.

        The filepath controls configuration and research/library classification
        as well as labels. Return findings from enabled installed checks;
        optional provider coverage is not established by an empty result.
        AST syntax errors become tool errors before checks run. AST parser
        acceptance does not establish compilation or runtime validity; this
        endpoint does not compile or execute the source."""
        from ...checker import lint_source
        from ...config import load_config
        from ...formatter import to_json

        try:
            ast.parse(source, filename=filepath)
        except SyntaxError as exc:
            location = f"{filepath}:{exc.lineno or '?'}:{exc.offset or '?'}"
            raise ValueError(
                f"Python source could not be parsed at {location}: {exc.msg}"
            ) from exc

        config = load_config(filepath)
        issues = lint_source(source, filepath=filepath, config=config)
        return to_json(issues, filepath)
