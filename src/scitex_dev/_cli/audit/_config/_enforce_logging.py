# -*- coding: utf-8 -*-
"""`audit.enforce-logging` — PS-220's per-package severity declaration.

PS-220 (no bare `print` in package source) is a STAGED rollout, not a
flag-day. Operator directive 2026-07-23 (Telegram 1691/1692)::

    「print に関しては順次やっていきましょうか。
      とりあえず warning で、移行できたものから red で」
    「red というか、エラー判定ってことですね」

i.e. the rule defaults to **warning** for every package, and each package
opts IN to **error** as it finishes migrating its prints to scitex-logging.
The measured blast radius is why: promoting to error ecosystem-wide would
newly fail 44 repos on 1856 findings (`GITIGNORED/ps220-blast-radius-
20260722.md`), so enforcement has to arrive per-package, on the schedule of
whoever does the migrating.

The declaration lives in `.scitex/dev/config.yaml`::

    audit:
      enforce-logging:
        level: error
        reason: "print migration complete (PR #412); all sites on scitex-logging"

A REASON IS MANDATORY on any level that deviates from the `warning` default
— `error` (opt in to being gated) and `off` (hide the findings entirely).
This follows the same doctrine as `audit.exemptions` and
`audit.capabilities` in `._loader`: an override is a written decision with a
named rationale, never a bare flag. A missing or whitespace-only reason is a
HARD CONFIG ERROR, not a silent default: the declaration does NOT take
effect (the project falls back to the staged default) AND the rejection is
surfaced as a violation, so a package cannot believe it is gated when it is
not — nor believe it is silenced when it is not.

`warning` needs no reason, because writing it changes nothing: it IS the
default. It is accepted in bare-scalar form for exactly that reason.
"""

from __future__ import annotations

# Accepted `level` values.
ENFORCE_LOGGING_VALUES = frozenset({"error", "warning", "off"})

# Levels that DEVIATE from the staged `warning` default and therefore demand
# a written reason. See the module docstring.
ENFORCE_LOGGING_REASONED_LEVELS = frozenset({"error", "off"})

_MAPPING_HINT = (
    "To deviate from the `warning` default, write the mapping form: "
    "`audit: {{enforce-logging: {{level: {level}, "
    'reason: "<why this package is at {level}>"}}}}`'
)


def _coerce_level(value: object) -> str | None:
    """Normalise one `level` scalar to a lowercase string (or None).

    YAML 1.1 parses bare ``off``/``no`` as boolean False and ``on``/``yes``
    as boolean True, so the level can arrive as a bool rather than a string.
    Reading it as a string only would make the knob silently no-op and fall
    back to the default — the exact class of silent-suppression bug this
    surface exists to prevent. Map the booleans explicitly.
    """
    if value is False:
        return "off"
    if value is True:
        return "error"
    if value is None:
        return None
    return str(value).strip().lower() or None


def _unknown_level(level: str, *, where: str) -> tuple[None, None, tuple[str, ...]]:
    """Reject an unrecognised level loudly rather than defaulting silently."""
    return (
        None,
        None,
        (
            f"PS-220: `{where}: {level}` is not a recognised level "
            f"(expected one of {sorted(ENFORCE_LOGGING_VALUES)}). The "
            f"declaration does NOT take effect.",
        ),
    )


def parse_enforce_logging(
    raw: object,
) -> tuple[str | None, str | None, tuple[str, ...]]:
    """Split `audit.enforce-logging` into ``(level, reason, rejections)``.

    ``level`` is None when nothing was declared OR when what was declared was
    REJECTED — in both cases the caller falls back to PS-220's staged default.
    ``rejections`` holds human-readable notices for every rejected form; an
    empty tuple means the block was clean.

    Accepted forms:

    * a mapping ``{level: <error|warning|off>, reason: <non-blank>}`` — the
      canonical form. ``reason`` is mandatory for ``error`` and ``off``.
    * a bare scalar ``warning`` — accepted reasonlessly because it is the
      default and therefore changes nothing.

    Rejected forms (each returns ``level=None`` plus a notice):

    * a bare scalar ``error`` / ``off`` (including the YAML 1.1 booleans
      ``on`` / ``true`` / ``off`` / ``no``) — carries no reason.
    * a mapping whose ``level`` is missing or unrecognised.
    * a mapping declaring ``error`` / ``off`` with a missing, empty, or
      whitespace-only ``reason``.
    """
    if raw is None:
        return None, None, ()

    if isinstance(raw, dict):
        level = _coerce_level(raw.get("level"))
        reason = str(raw.get("reason") or "").strip()
        if level is None:
            return (
                None,
                None,
                (
                    "PS-220: `audit.enforce-logging` mapping is missing `level` "
                    f"(one of {sorted(ENFORCE_LOGGING_VALUES)}). The "
                    f"declaration does NOT take effect.",
                ),
            )
        if level not in ENFORCE_LOGGING_VALUES:
            return _unknown_level(level, where="audit.enforce-logging.level")
        if level in ENFORCE_LOGGING_REASONED_LEVELS and not reason:
            return (
                None,
                None,
                (
                    f"PS-220: `audit.enforce-logging.level: {level}` REJECTED "
                    f"— `reason` is empty. Declaring `{level}` deviates from "
                    f"the staged `warning` default and must state WHY. The "
                    f"declaration does NOT take effect.",
                ),
            )
        return level, (reason or None), ()

    level = _coerce_level(raw)
    if level is None:
        return None, None, ()
    if level not in ENFORCE_LOGGING_VALUES:
        return _unknown_level(level, where="audit.enforce-logging")
    if level in ENFORCE_LOGGING_REASONED_LEVELS:
        return (
            None,
            None,
            (
                f"PS-220: `audit.enforce-logging: {level}` REJECTED — the bare "
                f"shorthand carries no reason. " + _MAPPING_HINT.format(level=level)
                + " The declaration does NOT take effect.",
            ),
        )
    return level, None, ()


__all__ = [
    "ENFORCE_LOGGING_VALUES",
    "ENFORCE_LOGGING_REASONED_LEVELS",
    "parse_enforce_logging",
]

# EOF
