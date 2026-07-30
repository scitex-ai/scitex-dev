#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The CLI-convention command-tree walker.

Extracted from `_audit.py` (1949 lines, against the repo's 512-line file
hook) so the walker can be EDITED. Three siblings were split out of the same
module for the same reason -- `_django/_checks.py`,
`_api/_checks/__init__.py`, `_startup_speed.py` -- and this follows that
precedent rather than inventing a layout.

A PURE MOVE: `_walk` and `_has_required_positional` are byte-identical to
what they were in `_audit.py`. No rule changed, no message changed, no
behaviour changed. That matters because a refactor and a behaviour change
landing together are indistinguishable in review.

`Violation` deliberately stays in `_audit.py`: 11 test files and
`_startup_speed.py` import it from there. Everything this module needs from
`_audit` is imported at module scope, which is cycle-free because `_audit`
forwards `_walk` LAZILY through its PEP 562 `__getattr__` -- so `_audit` is
always fully loaded before anything reaches for this module.
"""

from __future__ import annotations

import click

from . import FLAT_KEEPERS
from ._audit import (
    BANNED_LEAVES,
    SERVER_STARTUP_FLAGS,
    Violation,
    _check_help_format,
    _check_root_help_has_version,
    _check_universal_flags,
    _classify,
    _flag_names,
    _group_head_labels,
    _is_pass_through,
)

from ._coverage import HIDDEN, SurfaceCoverage

__all__ = ["_has_required_positional", "_walk"]


def _has_required_positional(cmd: click.BaseCommand) -> bool:
    """True iff ``cmd`` declares at least one required positional argument.

    A bare transitive verb at the top level is acceptable when it takes
    its object as a positional argument (`<cli> <verb> <OBJECT>`) — the
    object is right there, just not concatenated into the subcommand
    name. Compare ``pip install <pkg>``, ``git commit -m``, ``pytest
    <path>``: ergonomic, unambiguous, no `<verb>-<noun>` clutter. The
    auditor's §1 rule recognises this shape and skips the warning.
    """
    for p in getattr(cmd, "params", []) or []:
        if isinstance(p, click.Argument) and getattr(p, "required", False):
            return True
    return False


def _walk(
    cmd: click.BaseCommand,
    path: list[str],
    out: list[Violation],
    root_display: str,
    coverage: SurfaceCoverage | None = None,
) -> None:
    """Walk the command tree, appending violations AND recording coverage.

    ``coverage`` accumulates in place exactly as ``out`` does, so the two
    are threaded together and neither can be forgotten independently.

    It is optional only so existing callers keep working. A caller that
    omits it gets a verdict with no denominator, which
    :func:`._coverage.describe_or_unknown` renders as an explicit
    "NOT REPORTED" rather than as silence — the absent case must be
    louder than success, not indistinguishable from it.
    """
    # The command path is computed BEFORE the hidden check so a skip can be
    # recorded against a real name. The early return used to happen first,
    # which is why hidden commands left no trace at all: not inspected, not
    # counted, and the audited surface silently shrank.
    is_root = not path
    name = root_display if is_root else (cmd.name or "<root>")
    full = " ".join(path + [name]) if path else name

    # Skip hidden commands — not part of the public CLI surface
    # (typically deprecation redirects kept for back-compat). COUNTED as
    # skipped, never as inspected: a command nobody looked at must not
    # contribute to a figure that reads as "checked".
    if getattr(cmd, "hidden", False):
        if coverage is not None:
            coverage.record_skipped(full, HIDDEN)
        return
    is_group = isinstance(cmd, click.Group)

    # Recorded HERE, before any rule runs, because from this point the
    # command is genuinely inspected: §2 applies to every node including
    # the root and pass-throughs, so reaching this line IS coverage. The
    # pass-through return below narrows WHICH rules apply; it does not mean
    # nothing was checked.
    if coverage is not None:
        coverage.record_inspected(full)

    # §2 universal flag presence.
    _check_universal_flags(cmd, full, is_root, out)

    # §4 root --help must show the package version. Pass-through entry
    # points are exempt because their help is forwarded verbatim from
    # the upstream tool.
    if is_root and not _is_pass_through(cmd):
        _check_root_help_has_version(cmd, full, out)
        # §4b — the root, too, should build help from a CliHelp spec.
        from ._std_rules import check_spec_built_help

        check_spec_built_help(cmd, full, out)

    if not is_root:
        # §1c — pass-through entry points are exempt from §1 / §1d / §4.
        if _is_pass_through(cmd):
            return

        labels = _classify(name)
        is_leaf = not is_group
        is_compound = "-" in name

        # §1b banned bare leaves.
        if is_leaf and name.lower() in BANNED_LEAVES:
            redirect = {
                "version": "use the --version/-V flag at top level",
                "completion": "use 'install-shell-completion' or 'print-shell-completion'",
            }[name.lower()]
            out.append(
                Violation(full, "§1b", f"banned bare leaf '{name}' — {redirect}")
            )

        if is_leaf:
            # §1f — non-canonical verb synonym (WARN-only, data-driven
            # map seeded from the doctrine 06 synonym tables; respects
            # `verb_exceptions:` in .scitex/dev/cli-audit-dict.yaml).
            from ._std_rules import check_verb_synonym

            check_verb_synonym(name, full, out)

            # §1 — leaf-noun check. Historically the exemption
            # (`{verb-t, verb-i, verb, flat-keeper} & labels`) silently
            # passed multi-class noun-verb homonyms such as `board`
            # (Moby classifies as both noun and verb-t/verb-i), letting
            # `scitex-todo board --port 8051` slip through (operator
            # directive 13316). At TOP LEVEL (depth=1) AND for BARE
            # (non-compound) leaves the rule is tightened: a leaf
            # carrying `noun` in its labels is flagged regardless of
            # also-verb labels, because the operator's CLI grammar
            # requires top-level bare leaves to be unambiguously verbs.
            # Compound leaves like `print-shell-completion` are
            # explicitly excluded from PART A — the compound IS the
            # `<verb>-<object>` grammar the rule is asking for.
            top_level_leaf = len(path) == 1
            multi_class_homonym = (
                bool({"verb-t", "verb-i", "verb"} & labels) and "noun" in labels
            )
            if (
                "noun" in labels
                and (
                    (top_level_leaf and multi_class_homonym and not is_compound)
                    or not ({"verb-t", "verb-i", "verb", "flat-keeper"} & labels)
                )
                and name not in FLAT_KEEPERS
                and "flat-keeper" not in labels
            ):
                suffix = (
                    " — Moby classifies this as both noun AND verb; if the "
                    "verb meaning is intended in this CLI context, add to "
                    "`.scitex/dev/cli-audit-dict.yaml` under `intransitive_verbs:` "
                    "(same escape hatch `next` uses)."
                    if multi_class_homonym
                    else ""
                )
                out.append(
                    Violation(
                        full,
                        "§1",
                        f"leaf token looks like a noun — transitive action implied; "
                        f"use '<verb>-{name}' (e.g. start-{name}) or add a sibling verb"
                        + suffix,
                    )
                )

            # §1e — server-startup-flag heuristic. High-signal catch:
            # a noun-classified leaf at top level that accepts any of
            # `--port / --host / --bind / --serve / --daemon / --workers /
            # --listen / --addr / --address` is unambiguously starting a
            # service; the grammar should be `<noun> start` (group) or
            # `start-<noun>` (compound). Fires even when the §1 check
            # would have exempted the leaf via a Moby verb label —
            # operator directive 13316's exact pattern.
            if "noun" in labels and top_level_leaf:
                if SERVER_STARTUP_FLAGS & _flag_names(cmd):
                    out.append(
                        Violation(
                            full,
                            "§1e",
                            f"top-level noun leaf '{name}' accepts a server-"
                            f"startup flag (one of --port/--host/--bind/"
                            f"--serve/--daemon/--workers/--listen/--addr/"
                            f"--address) — that's a service-start verb in "
                            f"disguise; rename to 'start-{name}' or nest "
                            f"under a '{name}' group with a 'start' "
                            f"subcommand (e.g. '{name} start --port …').",
                        )
                    )
            if (
                ("verb-t" in labels or "verb" in labels)
                and not is_compound
                and len(path) == 1
                and "noun" not in labels
                and not _has_required_positional(cmd)
            ):
                out.append(
                    Violation(
                        full,
                        "§1",
                        f"bare transitive verb at top level — needs an object; "
                        f"use '{name}-<object>' or nest under a noun, OR add "
                        f"a required positional argument that IS the object "
                        f"(e.g. '{name} <SOURCE>')",
                    )
                )
        else:
            # §1 — a group (non-leaf) token must read as a NOUN. Classify by
            # the token's SEMANTIC HEAD, not by its hyphen-FIRST part: English
            # noun compounds are right-headed, so `login-guardrail` is a
            # *guardrail* (noun) whose leading `login` is a modifier — NOT a
            # verb-named group. `_classify` inherits verb-ness from the
            # hyphen-first fallback, which over-flagged such compound nouns
            # (confirmed regression on `login-guardrail`, breaking consumer
            # CI). Flag only when the HEAD itself is a whole-token verb and
            # not also a noun — so genuinely verb-named groups (`run`,
            # `build`, `login`) still fire, while compound nouns
            # (`login-guardrail`, `guardrail`, `gatekeeper`) pass.
            head_labels = _group_head_labels(name)
            if ({"verb-t", "verb-i", "verb"} & head_labels) and (
                "noun" not in head_labels
            ):
                out.append(
                    Violation(
                        full,
                        "§1",
                        "group token looks like a verb — non-leaf subcommands must be nouns",
                    )
                )

        if labels == {"unknown"}:
            out.append(
                Violation(
                    full,
                    "§1d",
                    f"'{name}' not in catalog, custom dict, or Moby POS — "
                    f"add to .scitex/dev/cli-audit-dict.yaml or rename",
                )
            )

        # §4 help format on leaves.
        _check_help_format(cmd, full, out)

        # §4b — spec-built help (leaves AND nested groups; the root is
        # covered above). WARN-only.
        from ._std_rules import check_spec_built_help

        check_spec_built_help(cmd, full, out)

    if is_group:
        next_path = [name] if is_root else path + [name]
        for sub in cmd.commands.values():
            _walk(sub, next_path, out, root_display, coverage)
