"""`audit.skip-rules` — the SANCTIONED per-rule deferral mechanism.

Deferring a rule to a named migration campaign is legitimate scheduling:
forcing every in-flight campaign (TQ-migration, CLI noun-verb, umbrella
thinning) to land in one commit is not a policy anyone chose. So
``audit-all`` honours a repo's declared skips natively.

What makes it sanctioned rather than a silencer is the RATIONALE. Every
entry must say WHY, in writing, in the config file::

    audit:
      skip-rules:
        PS-139: "TQ-migration campaign — tracked in scitex-hub#412"
        "§6":   "MCP parity lands with the umbrella-thinning wave"

The list-of-mappings form is equivalent and preferred when a reason is
long::

    audit:
      skip-rules:
        - rule: PS-139
          reason: "TQ-migration campaign — tracked in scitex-hub#412"

An entry with NO written rationale is REJECTED, loudly, naming the
offending entry. A deferral that cannot say why is exactly the
abandonment this mechanism exists to catch — and a bare rule id is
indistinguishable from debt somebody stopped thinking about.

Honouring is never silent: ``audit-all`` always prints a MASKED
INVENTORY (see ``.._cmds._audit_masking``) carrying the count, the rule
ids, the per-rule masked count and each written reason. A masked
violation nobody sees is the green-by-absence defect.

This is a DIFFERENT knob from the legacy ``audit.skip`` list (bare rule
codes, honoured only by ``audit-project``, applied silently) and from
``audit.capabilities`` (a declared package PROPERTY gating a fixed rule
set). ``audit.skip`` is left untouched for back-compat; new deferrals
should use ``skip-rules`` because only it carries a reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._loader import CONFIG_REL_PATH, _read_yaml

CONFIG_KEY = "skip-rules"


class SkipRuleConfigError(ValueError):
    """A ``audit.skip-rules`` entry is malformed or has no rationale.

    Raised rather than warned: a deferral we cannot read is not a
    deferral we may honour. The message always names the offending
    entry so the fix is mechanical.
    """


@dataclass(frozen=True)
class SkipRule:
    """One declared deferral: a rule code plus its written rationale."""

    rule: str
    reason: str


def _fail(detail: str) -> "SkipRuleConfigError":
    return SkipRuleConfigError(
        f"invalid `audit.{CONFIG_KEY}` entry: {detail}\n"
        f"  Every skip MUST carry a written rationale. Use either:\n"
        f"    audit:\n"
        f"      {CONFIG_KEY}:\n"
        f'        PS-139: "why this is deferred, and to which campaign"\n'
        f"  or:\n"
        f"    audit:\n"
        f"      {CONFIG_KEY}:\n"
        f"        - rule: PS-139\n"
        f'          reason: "why this is deferred, and to which campaign"'
    )


def _clean_reason(value: object, *, rule: str) -> str:
    """Return a non-empty reason string or raise naming ``rule``."""
    if value is None:
        raise _fail(f"{rule!r} has no `reason`")
    if not isinstance(value, str):
        raise _fail(f"{rule!r} has a non-string `reason` ({type(value).__name__})")
    reason = value.strip()
    if not reason:
        # Whitespace-only is not a rationale. Treated identically to a
        # missing one so "  " can't buy a silent pass.
        raise _fail(f"{rule!r} has an empty `reason`")
    return reason


def parse_skip_rules(raw: object) -> list[SkipRule]:
    """Parse the ``audit.skip-rules`` block into validated entries.

    Accepts the mapping form (``{rule: reason}``) and the list-of-
    mappings form (``[{rule: ..., reason: ...}]``). A bare list of rule
    ids — the shape the legacy ``audit.skip`` uses — is REJECTED,
    because it carries no rationale.

    Raises
    ------
    SkipRuleConfigError
        On any entry that is malformed or lacks a written rationale.
    """
    if raw is None or raw == [] or raw == {}:
        return []

    entries: list[SkipRule] = []

    if isinstance(raw, dict):
        for rule, reason in raw.items():
            rule_id = str(rule).strip()
            if not rule_id:
                raise _fail("an entry has an empty rule id")
            entries.append(SkipRule(rule_id, _clean_reason(reason, rule=rule_id)))
        return entries

    if isinstance(raw, list):
        for idx, item in enumerate(raw):
            if isinstance(item, str):
                # The legacy bare-id shape. This is the case the whole
                # mechanism exists to reject: it says WHAT is deferred
                # but never WHY.
                raise _fail(
                    f"{item.strip()!r} (position {idx}) is a bare rule id "
                    f"with no rationale"
                )
            if not isinstance(item, dict):
                raise _fail(f"position {idx} is a {type(item).__name__}, not a mapping")
            rule_id = str(item.get("rule") or "").strip()
            if not rule_id:
                raise _fail(f"position {idx} has no `rule` key")
            entries.append(SkipRule(rule_id, _clean_reason(item.get("reason"), rule=rule_id)))
        return entries

    raise _fail(f"expected a mapping or list, got {type(raw).__name__}")


def load_skip_rules(repo: Path) -> list[SkipRule]:
    """Read + validate ``audit.skip-rules`` from ``<repo>`` config.

    Returns an empty list when the repo declares none. Raises
    :class:`SkipRuleConfigError` when it declares a malformed one — a
    repo whose deferral config we cannot trust must not be graded as if
    it had no deferrals at all.
    """
    raw = _read_yaml(Path(repo) / CONFIG_REL_PATH)
    if not raw:
        return []
    audit = raw.get("audit") or {}
    if not isinstance(audit, dict):
        return []
    return parse_skip_rules(audit.get(CONFIG_KEY))


__all__ = [
    "CONFIG_KEY",
    "SkipRule",
    "SkipRuleConfigError",
    "load_skip_rules",
    "parse_skip_rules",
]
