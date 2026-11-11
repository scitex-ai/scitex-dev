"""Adapt owned auditor JSON findings to the existing masking classifier.

Only emitted findings are classified; inventories such as violations_total
must not bypass an auditor's severity filter. Malformed output remains an
unreadable failure, never a clean or fully deferred result.
"""

from __future__ import annotations

import json
import re

_LEVELS = {
    "error": "ERRO",
    "e": "ERRO",
    "warning": "WARN",
    "warn": "WARN",
    "w": "WARN",
    "info": "INFO",
    "i": "INFO",
}


def _finding_lines(auditor: str, payload: object) -> list[str]:
    if not isinstance(payload, dict):
        raise TypeError("auditor JSON must be an object")
    records = (
        payload.get("results")
        if auditor in {"audit-cli", "audit-mcp-tools"}
        else [payload]
    )
    if not isinstance(records, list) or not records:
        raise ValueError("auditor JSON has no result records")
    lines = [f"INFO: {auditor}: structured findings inspected"]
    for record in records:
        if not isinstance(record, dict) or not isinstance(
            record.get("violations"), list
        ):
            raise TypeError("auditor JSON has no findings list")
        for row in record["violations"]:
            if not isinstance(row, dict):
                raise TypeError("auditor JSON finding must be an object")
            rule, severity = row.get("rule"), row.get("severity")
            if (
                not isinstance(rule, str)
                or not rule
                or any(
                    c.isspace() or c in "[]" or ord(c) < 32 or ord(c) == 127
                    for c in rule
                )
                or not re.search(r"[\d§]", rule)
            ):
                raise ValueError("auditor JSON finding has no attributable rule")
            if not isinstance(severity, str) or severity.lower() not in _LEVELS:
                raise ValueError("auditor JSON finding has unknown severity")
            # Escape arbitrary details so they cannot inject a second finding
            # or a bracketed rule that could change deferral attribution.
            detail = (
                json.dumps(row, ensure_ascii=True, sort_keys=True)
                .replace("[", r"\u005b")
                .replace("]", r"\u005d")
            )
            lines.append(f"{_LEVELS[severity.lower()]}: [{rule}] {detail}")
    return lines


def captured_json_result(
    auditor: str, exit_code: int, stdout: str, stderr: str
) -> dict:
    """Keep original JSON and exits; derive classification from typed rows."""
    result = {"exit": exit_code}
    try:
        result["data"] = json.loads(stdout.strip() or "null")
        lines = _finding_lines(auditor, result["data"])
    except (ValueError, TypeError) as error:
        if "data" not in result:
            result["raw"] = stdout.strip()
        result["exit"] = exit_code or 1
        result["error"] = str(error)
        lines = ["[unreadable JSON finding] " + json.dumps(str(error))]
    result["_raw"] = "\n".join([*lines, stderr or ""])
    return result
