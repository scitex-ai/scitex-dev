# -*- coding: utf-8 -*-
"""Diagnostics for legacy `audit.*` keys that do not mask what operators
expect.

Two shapes, one lesson — measured fleet-wide (cards, app):

* ``audit.skip`` (bare rule ids) is honoured only by ``audit-project``
  (and ``audit-python-apis``), silently: no written reason is recorded
  and no masked inventory is printed. Findings of every OTHER auditor
  (cli, skills, …) and the ``audit-all`` masking layer ignore it
  outright. An operator who writes ``audit.skip: [PS-210]`` and reads a
  green ``audit-all`` may be green-by-absence.
* ``audit.exemptions`` (per-site, reasoned) is honoured ONLY by checks
  that consult it — the armed set below. An entry for any other rule
  sits in the file looking handled while suppressing nothing (app's
  PS-210 comment documents exactly this trap: the entry "would sit in
  this file looking handled while suppressing nothing, and a dead
  exemption is worse than none — so it is not written").

The sanctioned deferral is ``audit.skip-rules`` (rule + written
reason; honoured natively by ``audit-all`` with a masked inventory).
These notices point there. They are notices, not findings: exit codes
and violation counts are unchanged — but the config stops reading as
done when it is not.
"""

from __future__ import annotations

from pathlib import Path

from ._loader import CONFIG_REL_PATH, _read_yaml

#: Rules whose checks consult ``audit.exemptions`` to SUPPRESS a finding
#: (via ``config.exemption_for``). An entry for any other rule is dead
#: config. Pinned by ``test__legacy_keys`` against the real consumers —
#: adding an arm without extending this set fails that test on purpose.
#:
#: PS-220 is deliberately ABSENT: it reports malformed exemption blocks
#: but its own docstring forbids suppression ("Configuration cannot
#: downgrade, disable, or manually exempt PS-220"), so an entry for it
#: suppresses nothing either.
EXEMPTION_ARMED_RULES: frozenset[str] = frozenset(
    {
        "PS-221",
        "PS-222",
        "PS-223",
        "PS-224",
        "PS-230",
        "PS-231",
        "PS-HOOK-010",
        "PS-HOOK-011",
        "PS-HOOK-012",
    }
)


def legacy_audit_key_notices(repo: Path) -> list[str]:
    """Return human-readable notices for legacy/dead `audit.*` keys.

    Empty list when the repo declares nothing legacy — the common case
    stays silent. Every notice names the key, says what it does NOT do,
    and points at ``audit.skip-rules``.
    """
    raw = _read_yaml(Path(repo) / CONFIG_REL_PATH)
    if not raw:
        return []
    audit = raw.get("audit") or {}
    if not isinstance(audit, dict):
        return []

    notices: list[str] = []

    skip = audit.get("skip") or []
    if isinstance(skip, str):
        skip = [skip]
    if isinstance(skip, list) and [s for s in skip if str(s).strip()]:
        ids = sorted({str(s).strip() for s in skip if str(s).strip()})
        notices.append(
            f"`audit.skip` lists {len(ids)} rule(s) ({', '.join(ids)}): "
            "legacy key — honoured only by `audit-project` (and "
            "`audit-python-apis`), silently (no reason recorded, no "
            "masked inventory), and ignored by `audit-all` and every "
            "other auditor. Migrate each entry to `audit.skip-rules` "
            "with a written reason; `audit-all` then masks and "
            "inventories them."
        )

    exemptions = audit.get("exemptions")
    if exemptions is not None:
        if not isinstance(exemptions, dict):
            notices.append(
                f"`audit.exemptions` is not a mapping (got "
                f"{type(exemptions).__name__}) — the block took effect "
                "NOWHERE. Write `{RULE:} [{path, line, reason}, ...]` per "
                "rule, or defer via `audit.skip-rules` with a reason."
            )
        else:
            dead = sorted(
                str(rule).strip()
                for rule in exemptions
                if str(rule).strip() not in EXEMPTION_ARMED_RULES
            )
            for rule in dead:
                notices.append(
                    f"`audit.exemptions` entry for `{rule}` suppresses "
                    "nothing — no check consults exemptions for that "
                    "rule. Defer via `audit.skip-rules` (with a written "
                    "reason) or drop the entry."
                )

    return notices


__all__ = ["EXEMPTION_ARMED_RULES", "legacy_audit_key_notices"]
