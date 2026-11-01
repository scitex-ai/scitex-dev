"""Execute leaf-owned checks; policy remains in the declaring distribution."""

from __future__ import annotations

import fnmatch
import importlib

import scitex_logging as slogging

from ._discover import discover_hooks
from ._spec import resolve_asset

_logger = slogging.getLogger(__name__)


def dispatch(payload, *, provider):
    """Return failures for matching executable rules of one required provider."""
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("tool_name"), str)
        or not payload["tool_name"]
    ):
        return ["Cannot verify malformed native tool payload"]
    event = payload.get("hook_event_name", "pre_tool_call")
    event = {
        "PreToolUse": "pre-tool-use",
        "PostToolUse": "post-tool-use",
        "pre_tool_call": "pre-tool-use",
        "post_tool_call": "post-tool-use",
    }.get(event, event)
    tool = payload.get("tool_name", "")
    rules = [r for r in discover_hooks() if r.provider == provider]
    if not rules:
        return [
            f"Required hook provider {provider!r} is not installed or could not load"
        ]
    findings = []
    results = {}
    notices = set()
    for rule in rules:
        if rule.event != event or not any(
            fnmatch.fnmatchcase(tool, pattern) for pattern in rule.matches
        ):
            continue
        if rule.script and resolve_asset(rule) is None:
            findings.append(f"Hook {rule.id!r} declares an unavailable script asset")
            continue
        if not rule.check:
            findings.append(f"Hook {rule.id!r} has no in-process check binding")
            continue
        try:
            if rule.check not in results:
                module, name = rule.check.split(":", 1)
                check = getattr(importlib.import_module(module), name)
                results[rule.check] = check(payload)
            result = results[rule.check]
            if not isinstance(result, (list, tuple)) or not all(
                isinstance(item, str) for item in result
            ):
                raise TypeError(
                    "A hook check must return a sequence of violation strings"
                )
            for item in result:
                if rule.severity == "deny":
                    if item not in findings:
                        findings.append(item)
                elif (rule.severity, item) not in notices:
                    emit = (
                        slogging.getLogger(__name__).warning
                        if rule.severity == "warn"
                        else slogging.getLogger(__name__).info
                    )
                    emit("%s", item)
                    notices.add((rule.severity, item))
        except Exception as exc:  # stx-allow: fallback (reason: provider errors must fail closed rather than permit unverified tool calls)
            _logger.exception("Hook %s verification failed", rule.id)
            findings.append(
                f"Hook {rule.id!r} failed ({type(exc).__name__}); refusing an unverified tool call"
            )
    return findings
