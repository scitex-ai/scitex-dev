# -*- coding: utf-8 -*-
"""`audit.exemptions` — per-SITE rule exemption with a MANDATORY reason.

Operator directive 2026-07-22 (the no-bare-print mandate). This follows the
``audit.capabilities`` doctrine (fixed scope + a VISIBLE notice) rather than
the blanket ``audit.skip``: an exemption names ONE rule at ONE file:line and
must SAY WHY. It cannot silence a rule repo-wide, and it cannot be written
without a reason::

    audit:
      exemptions:
        PS-220:
          - path: src/pkg/_cli/_report.py
            line: 88
            reason: "renders the --json payload a shell consumes"

Nothing here fails QUIETLY
--------------------------
Every malformed shape is REJECTED with a notice that NAMES THE TYPE IT
RECEIVED and NAMES THE LIKELY MISTAKE; the notices ride
:attr:`ProjectConfig.exemption_errors` and each rule's config-error arm emits
them at ``E``. An entry whose ``reason`` is missing, empty, or whitespace-only
is rejected the same way — it does NOT exempt the site.

This module exists because the opposite was shipped. Until 2026-07-29 a
non-mapping ``exemptions:`` block returned "no exemptions, no errors": every
entry the author wrote vanished with NO output at all. scitex-hub wrote the
list form::

    audit:
      exemptions:
        - rule: PS-224
          path: .github/workflows/e2e-mobile.yml::playwright-mobile
          reason: "..."

...and could only discover why it did nothing by downloading the wheel and
reading this parser. A config that CANNOT take effect must never be
indistinguishable from a config that DID.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Marker opening every notice that concerns the WHOLE ``audit.exemptions``
#: block rather than one rule's entries.
#:
#: Entry-level notices are prefixed with their rule code, and each rule's
#: config-error arm filters on that code. A BLOCK-level failure belongs to no
#: single rule — it drops EVERY rule's exemptions — so a ``startswith(rule)``
#: filter would swallow it and reproduce the exact silent drop this reporting
#: exists to prevent. :func:`exemption_notice_applies` is the predicate every
#: arm uses instead of a bare ``startswith``.
EXEMPTION_BLOCK_PREFIX = "audit.exemptions:"


@dataclass(frozen=True)
class Exemption:
    """One accepted ``audit.exemptions`` entry (rule + site + reason)."""

    rule: str
    path: str
    line: int
    reason: str


def exemption_notice_applies(notice: str, rule: str) -> bool:
    """True iff ``rule``'s config-error arm must report ``notice``.

    An entry-level notice names the ONE rule whose entry was rejected, so only
    that rule reports it. A block-level notice (see
    :data:`EXEMPTION_BLOCK_PREFIX`) is reported by EVERY arm — the malformed
    block cost every rule its exemptions, so every rule's reader must see it.
    """
    return notice.startswith(EXEMPTION_BLOCK_PREFIX) or notice.startswith(rule)


def format_exemption_notice(notice: str, rule: str) -> str:
    """Render one ``exemption_errors`` notice as a config-error finding detail.

    Shared by the per-rule config-error arms (PS-220 / PS-222 / PS-223 /
    PS-224) so the four of them cannot drift apart in what they tell a reader.
    """
    if notice.startswith(EXEMPTION_BLOCK_PREFIX):
        return (
            f"Invalid `audit.exemptions` block — {notice} The block was "
            f"dropped WHOLESALE, so NO {rule} exemption took effect."
        )
    return (
        f"Invalid `audit.exemptions` entry — {notice} The entry does NOT "
        f"exempt anything."
    )


def _typed(value: object) -> str:
    """Name the RECEIVED type with its article — ``"a list"`` / ``"an int"``.

    A config error that does not say what it got makes the author guess; hub
    had to download the wheel and read this parser to learn its block was a
    list.
    """
    name = type(value).__name__
    article = "an" if name[:1].lower() in "aeiou" else "a"
    return f"{article} {name}"


def _block_notice(raw: object) -> str:
    """The block-level notice for a non-mapping ``audit.exemptions:`` value."""
    if isinstance(raw, list):
        hint = "Did you write `- rule: PS-224` instead of `PS-224:`?"
    elif isinstance(raw, str):
        hint = (
            "Did you write `exemptions: PS-224` instead of a `PS-224:` block "
            "of entries?"
        )
    else:
        hint = (
            "Each rule code is a KEY whose value is a list of entries, e.g. "
            "`PS-224:` then `- path: ...` / `line: 0` / `reason: ...`."
        )
    return (
        f"{EXEMPTION_BLOCK_PREFIX} expected a mapping of rule-code -> "
        f"[entries], got {_typed(raw)}. {hint}"
    )


def _rule_value_notice(rule: str, entries: object) -> str:
    """Notice for a rule whose value is not a LIST of entries."""
    if isinstance(entries, dict):
        hint = (
            f"Did you write the entry directly under `{rule}:` instead of as "
            f"a list item `- path: ...`?"
        )
    else:
        hint = (
            "Write each entry as a list item: `- path: ...` / `line: 0` / "
            "`reason: ...`."
        )
    return f"{rule}: expected a list of entries, got {_typed(entries)}. {hint}"


def _entry_notice(label: str, entry: object) -> str:
    """Notice for a list item that is not an entry MAPPING."""
    if isinstance(entry, str):
        hint = f"Did you write `- {entry}` instead of `- path: {entry}`?"
    else:
        hint = "Write each entry as `- path: ...` / `line: 0` / `reason: ...`."
    return (
        f"{label}: expected an entry mapping with `path`/`line`/`reason`, "
        f"got {_typed(entry)}. {hint}"
    )


def parse_exemptions(
    raw: object,
) -> tuple[tuple[Exemption, ...], tuple[str, ...]]:
    """Split an ``audit.exemptions`` block into (accepted, rejection notices).

    Shape is ``{rule_code: [{path, line, reason}, ...]}``. Anything that does
    not match — a non-mapping block, a non-list rule value, a non-mapping
    entry, a missing/blank ``reason``, an unparseable ``line`` — is REJECTED
    with a human-readable notice rather than silently dropped or silently
    honoured. Only an ABSENT block (``None``) is silent: nothing was written,
    so nothing was lost.
    """
    if raw is None:
        return (), ()
    if not isinstance(raw, dict):
        return (), (_block_notice(raw),)
    accepted: list[Exemption] = []
    errors: list[str] = []
    for rule, entries in raw.items():
        rule = str(rule).strip()
        if not isinstance(entries, list):
            errors.append(_rule_value_notice(rule, entries))
            continue
        for idx, entry in enumerate(entries):
            label = f"{rule}[{idx}]"
            if not isinstance(entry, dict):
                errors.append(_entry_notice(label, entry))
                continue
            path = str(entry.get("path") or "").strip()
            reason = str(entry.get("reason") or "").strip()
            raw_line = entry.get("line")
            if not path:
                errors.append(f"{label}: missing `path`.")
                continue
            if not reason:
                # The whole point of the surface: no reason, no exemption.
                errors.append(
                    f"{label} ({path}): REJECTED — `reason` is empty; an "
                    f"exemption must state WHY this site is exempt."
                )
                continue
            try:
                line = int(raw_line)
            except (TypeError, ValueError):
                errors.append(
                    f"{label} ({path}): `line` must be an integer, got "
                    f"{_typed(raw_line)}."
                )
                continue
            accepted.append(
                Exemption(
                    rule=rule,
                    path=path.replace("\\", "/"),
                    line=line,
                    reason=reason,
                )
            )
    return tuple(accepted), tuple(errors)


__all__ = [
    "EXEMPTION_BLOCK_PREFIX",
    "Exemption",
    "exemption_notice_applies",
    "format_exemption_notice",
    "parse_exemptions",
]

# EOF
