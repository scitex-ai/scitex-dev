"""Exact opt-in executable rule subsets within an existing hook provider."""

from __future__ import annotations


def select_rules(rules, *, provider, rule_ids=None):
    """Validate an explicit subset; None preserves strict whole-provider behavior."""
    owned = [rule for rule in rules if rule.provider == provider]
    if rule_ids is None:
        return owned
    if not isinstance(rule_ids, (list, tuple)) or not rule_ids:
        raise ValueError("rule_ids must be a nonempty explicit list or tuple")
    if any(
        not isinstance(item, str) or not item.strip() or item != item.strip()
        for item in rule_ids
    ):
        raise ValueError("rule_ids must contain nonempty exact rule IDs")
    if len(set(rule_ids)) != len(rule_ids):
        raise ValueError("Duplicate hook rule selection is not permitted")
    available = {rule.id for rule in owned}
    if not set(rule_ids) <= available:
        raise ValueError("Selected rule IDs are unknown or not owned by this provider")
    selected = [rule for rule in owned if rule.id in rule_ids]
    if any(not rule.check for rule in selected):
        raise ValueError("Selected hook rules must expose executable check bindings")
    return selected
