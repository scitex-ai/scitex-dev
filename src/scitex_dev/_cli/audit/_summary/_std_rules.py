"""CLI-standardization audit rules (slice 4 of the CLI-standardization plan).

New rules layered on top of the `_audit.py` walker — kept in a sibling
module so the legacy-oversized engine does not grow further:

- §1f  non-canonical verb synonym (WARN) — data-driven map seeded from the
       doctrine synonym tables in
       ``_skills/general/03_interface/02_cli/06_noun-verb-catalog.md``.
       Respects a ``verb_exceptions:`` key in the per-repo
       ``.scitex/dev/cli-audit-dict.yaml`` (each entry needs a ``# why``
       comment; entries lacking one are themselves warned about).
- §4b  help not built from spec (WARN) — every command should construct
       help via ``CliHelp`` (``from scitex_dev.ecosystem import CliHelp``
       — NOT ``scitex_dev.ecosystem.help_spec``, which is not importable:
       ``scitex_dev.ecosystem`` is a module, not a package); the
       ``_help_spec`` attribute set by ``SpecCommand`` / ``SpecGroup`` is
       the static evidence. Subsumes the ``_has_example`` sniff for
       spec-built commands (spec validation already guarantees examples).
- §5   deprecated-alias static metadata verification — every command
       carrying ``_deprecated_alias`` (set by
       ``scitex_dev.ecosystem.deprecated_alias``) must name a target that
       exists in the command tree and declare ``remove_in``.
- §5   behavioral assessment for hidden leaves (pure decision logic) —
       phase="warn" aliases MUST exit 0 and print 'deprecated' on stderr;
       phase="error" MUST exit 2; missing metadata keeps the legacy
       expectation (non-zero + redirect hint on stderr).
- §12  canonical `gui` command group — see the sibling module
       `_gui_group.py` (kept separate to stay under the repo's own
       512-line file limit). Doctrine:
       ``_skills/general/03_interface/02_cli/19_gui-commands.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

import click
import yaml

__all__ = [
    "VERB_SYNONYMS",
    "assess_hidden_leaf",
    "check_deprecated_alias_metadata",
    "check_spec_built_help",
    "check_verb_exception_comments",
    "check_verb_synonym",
    "load_verb_exceptions",
]


# ----------------------------------------------------------------------- #
# §1f — non-canonical verb synonyms                                        #
# ----------------------------------------------------------------------- #

# Mirrors `_CONVENTION_SYNONYMS` (flags) but for verb tokens. Seeded from
# the doctrine 06_noun-verb-catalog.md tables (canonical verb definitions,
# terminal-state verbs, and the "Avoid synonyms" table) — do NOT invent
# entries here; every row traces to a doctrine line. Lookup order: the
# FULL leaf name first (catches `show-status`, `sync-to`), then the verb
# token (first hyphen part — catches `resolve-card` via `resolve`).
VERB_SYNONYMS: dict[str, str] = {
    # --- full-leaf-name forms (compound / alias spellings) ---
    "show-status": "status (polysemous leaf under the noun group)",
    "sync-status": "status (polysemous leaf under the noun group)",
    "ss": "status (no short aliases — §1d grammar rules)",
    "sync-to": "push-<object> (directional transfer is push/pull, not sync)",
    "sync-from": "pull-<object> (directional transfer is push/pull, not sync)",
    "sync-up": "push-<object> (directional transfer is push/pull, not sync)",
    "sync-down": "pull-<object> (directional transfer is push/pull, not sync)",
    "pull-push": "sync-<object> (bidirectional reconcile is sync-<object>)",
    # --- verb tokens: list ---
    "ls": "list",
    "enumerate": "list",
    "all": "list",
    # --- verb tokens: show ---
    "display": "show",
    "print": "show",
    "cat": "show",
    "view": "show",
    # --- verb tokens: delete ---
    "rm": "delete",
    "drop": "delete",
    "destroy": "delete",
    "kill": "delete (reserve `kill` for OS-signal semantics)",
    # --- verb tokens: create ---
    "new": "create",
    "make": "create",
    "gen": "create (use `generate` if needed)",
    # --- verb tokens: update ---
    "modify": "update",
    "edit": "update",
    "set": "update (use `set` only for single-key config writes)",
    # --- verb tokens: sync ---
    "reconcile": "sync-<object>",
    "refresh": "sync-<object>",
    # --- verb tokens: validate ---
    "verify": "validate (one checking verb ecosystem-wide)",
    "check": "validate (one checking verb ecosystem-wide)",
    # --- verb tokens: install / init / uninstall ---
    "setup": "install|init (install = add to existing system; init = new skeleton)",
    "bootstrap": "install|init (install = add to existing system; init = new skeleton)",
    "teardown": "uninstall",
    # --- terminal-state verbs (exactly done / close) ---
    "resolve": "done",
    "complete": "done",
    "finish": "done",
    "end": "done",
    "cancel": "close (close --reason <r> carries the reason)",
    "wontfix": "close (close --reason <r> carries the reason)",
}

# Canonical commands the doctrine itself REQUIRES (§1a) whose verb token
# collides with a synonym row above. `print-shell-completion` is mandated
# by the §1a introspection check, so its `print` head must not warn.
_BUILTIN_VERB_EXCEPTIONS = frozenset(
    {
        "print-shell-completion",
        "install-shell-completion",
    }
)

_VERB_EXCEPTIONS_KEY = "verb_exceptions"
_WHY_COMMENT_MARKER = "# why"


def _dict_candidate_paths() -> list[Path]:
    """The layered custom-dict locations — one owner, in `._dict_root`.

    Kept as a named indirection because this module's rule bodies and
    the existing tests both call it. The project layer is rooted at the
    tree pinned by `_dict_root.use_dict_root` (the `--path` checkout),
    falling back to the cwd only when nothing is pinned; the list stays
    deduplicated by resolved path so a project-root-IS-home layout is
    read once rather than doubling every missing-`# why` finding.
    """
    from ._dict_root import dict_candidate_paths

    return dict_candidate_paths()


def load_verb_exceptions() -> tuple[set[str], list[tuple[str, Path]]]:
    """Read `verb_exceptions:` entries from the layered cli-audit-dict.yaml.

    Returns ``(exceptions, missing_why)`` where ``exceptions`` is the set
    of exempted tokens/leaf-names and ``missing_why`` lists
    ``(entry, dict_path)`` pairs whose YAML line lacks a ``# why``
    comment. YAML strips comments at parse time, so comment presence is
    verified with a raw-text scan of the dict file: the line declaring
    the entry (``- <entry>``) must carry ``# why`` inline.
    """
    exceptions: set[str] = set()
    missing_why: list[tuple[str, Path]] = []
    for path in _dict_candidate_paths():
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
        except (OSError, yaml.YAMLError):
            continue
        entries = data.get(_VERB_EXCEPTIONS_KEY) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, str):
                continue
            token = entry.strip().lower()
            exceptions.add(token)
            if not _entry_line_has_why_comment(raw, entry):
                missing_why.append((token, path))
    return exceptions, missing_why


def _entry_line_has_why_comment(raw: str, entry: str) -> bool:
    """True when the raw YAML line declaring ``entry`` carries `# why`."""
    pat = re.compile(
        r"^\s*-\s*['\"]?" + re.escape(entry) + r"['\"]?\s*(#.*)?$"
    )
    for line in raw.splitlines():
        m = pat.match(line)
        if m:
            comment = m.group(1) or ""
            return _WHY_COMMENT_MARKER in comment
    return False


def check_verb_synonym(name: str, full: str, out: list) -> None:
    """§1f — warn when a leaf uses a non-canonical verb synonym.

    Lookup order: the full leaf name, then the verb token (first hyphen
    part). Exemptions: the built-in §1a-mandated commands and any entry
    in the per-repo ``verb_exceptions:`` list.
    """
    from ._audit import Violation, _verb_token

    name_lc = name.lower()
    if name_lc in _BUILTIN_VERB_EXCEPTIONS:
        return
    verb = _verb_token(name)
    hit_token = name_lc if name_lc in VERB_SYNONYMS else (
        verb if verb in VERB_SYNONYMS else None
    )
    if hit_token is None:
        return
    exceptions, _missing_why = load_verb_exceptions()
    if name_lc in exceptions or verb in exceptions:
        return
    out.append(
        Violation(
            full,
            "§1f",
            f"non-canonical verb synonym {hit_token!r} — use "
            f"{VERB_SYNONYMS[hit_token]} (doctrine 06_noun-verb-catalog; "
            f"exempt via `verb_exceptions:` in .scitex/dev/cli-audit-dict.yaml "
            f"with a `# why` comment)",
        )
    )


def check_verb_exception_comments(package: str, out: list) -> None:
    """§1f — warn once per `verb_exceptions:` entry lacking a `# why` comment.

    Emitted at the package level (not per leaf) so a single undocumented
    exception produces exactly one finding per audit run.
    """
    from ._audit import Violation

    _exceptions, missing_why = load_verb_exceptions()
    for entry, path in missing_why:
        out.append(
            Violation(
                package,
                "§1f",
                f"verb_exceptions entry {entry!r} in {path} lacks a "
                f"`# why` comment — every exception must document its "
                f"justification inline (e.g. `- {entry}  # why: ...`)",
            )
        )


# ----------------------------------------------------------------------- #
# §4b — help not built from spec                                            #
# ----------------------------------------------------------------------- #


def check_spec_built_help(cmd: click.BaseCommand, full: str, out: list) -> None:
    """§4b — warn when a command's help is not built from a CliHelp spec.

    ``SpecCommand`` / ``SpecGroup`` set ``cmd._help_spec``; its absence
    means free-form help text, which drifts (missing examples, ad-hoc
    exit-code shapes). WARN-only.

    THE REMEDIATION NAMES AN IMPORT, SO THE IMPORT MUST RESOLVE. It used to
    read ``scitex_dev.ecosystem.help_spec``, which raises::

        ModuleNotFoundError: No module named 'scitex_dev.ecosystem.help_spec';
        'scitex_dev.ecosystem' is not a package

    ``scitex_dev.ecosystem`` is a MODULE — it re-exports 22 names including
    ``CliHelp``, but has no ``__path__``, so nothing can be addressed
    beneath it. The private module is ``scitex_dev._ecosystem.help_spec``,
    and the public re-export exists precisely so nobody needs it.

    Reported by scitex-ui 2026-08-15 and confirmed here. The cost was not
    cosmetic: they copied the hint onto a card on 2026-07-29, ran the
    import, read ``ModuleNotFoundError`` as "help_spec is not public API
    yet", and DEFERRED THE WORK FOR TWO WEEKS. ``CliHelp`` was public the
    whole time, including in the 0.42.0 their container runs.

    A wrong name in a hint does not merely fail to help — it fails in the
    direction that makes the status quo look correct, which is the one
    direction nobody re-checks.
    """
    from ._audit import Violation

    # THE ATTRIBUTE IS A CONTRACT, NOT A LATCH.
    #
    # This is a `getattr`, not an isinstance check, so ANY object hung on
    # `_help_spec` satisfies it. That duck-typing is deliberate and load-
    # bearing: it lets a package compose `_SpecRendered` into its own base
    # (sac's lazy root group needs exactly that, 2026-08-18). It is NOT
    # permission to assign a placeholder and go green.
    #
    # Recorded because sac identified the loophole, could have taken it
    # silently, and declined — their words: it "would turn a real rule into
    # a gate that cannot fail". They were right, and nobody would have
    # found out, because the failure mode of that shortcut IS a pass.
    #
    # The next reader will have the same idea and may not have the same
    # restraint, so the warning lives next to the check rather than in a
    # conversation neither of us can find in a month.
    if getattr(cmd, "_help_spec", None) is not None:
        return
    out.append(
        Violation(
            full,
            "§4b",
            "help is free-form text — construct via CliHelp "
            "(from scitex_dev.ecosystem import CliHelp, SpecCommand, "
            "SpecGroup, Example)",
        )
    )


# ----------------------------------------------------------------------- #
# §5 — deprecated-alias static metadata verification                        #
# ----------------------------------------------------------------------- #


def check_deprecated_alias_metadata(
    root: click.BaseCommand, package: str, out: list
) -> None:
    """§5 — statically verify every ``_deprecated_alias`` in the tree.

    Requirements (metadata is set by
    ``scitex_dev.ecosystem.deprecated_alias``):

    - ``remove_in`` is set (the ladder always names the deadline).
    - ``target`` resolves to a command in the tree: as a path from the
      alias's parent group, as a path from the root, or (single-word
      targets) as ANY command name at any depth.
    """
    from ._audit import Violation

    def _walk_aliases(cmd: click.BaseCommand, path: list[str], parent) -> None:
        meta = getattr(cmd, "_deprecated_alias", None)
        if meta is not None:
            full = " ".join([package, *path]) if path else package
            if not str(meta.get("remove_in") or "").strip():
                out.append(
                    Violation(
                        full,
                        "§5",
                        "deprecated alias metadata lacks `remove_in` — "
                        "every ladder phase names the removal version",
                    )
                )
            target = str(meta.get("target") or "").strip()
            if not target:
                out.append(
                    Violation(
                        full,
                        "§5",
                        "deprecated alias metadata lacks `target`",
                    )
                )
            elif not _target_exists(root, parent, target):
                out.append(
                    Violation(
                        full,
                        "§5",
                        f"deprecated alias target {target!r} not found in "
                        f"the command tree — the alias forwards nowhere",
                    )
                )
        if isinstance(cmd, click.Group):
            for name, sub in cmd.commands.items():
                _walk_aliases(sub, path + [name], cmd)

    _walk_aliases(root, [], None)


def _resolve_path(start: click.BaseCommand | None, parts: list[str]) -> bool:
    """True when ``parts`` resolves as a command path under ``start``."""
    node = start
    for part in parts:
        if not isinstance(node, click.Group):
            return False
        nxt = node.commands.get(part)
        if nxt is None:
            return False
        node = nxt
    return node is not start


def _any_command_named(cmd: click.BaseCommand, name: str) -> bool:
    """True when any command at any depth under ``cmd`` is named ``name``."""
    if isinstance(cmd, click.Group):
        if name in cmd.commands:
            return True
        return any(_any_command_named(sub, name) for sub in cmd.commands.values())
    return False


def _target_exists(
    root: click.BaseCommand,
    parent: click.BaseCommand | None,
    target: str,
) -> bool:
    parts = target.split()
    if parent is not None and _resolve_path(parent, parts):
        return True
    if _resolve_path(root, parts):
        return True
    if len(parts) == 1:
        return _any_command_named(root, parts[0])
    return False


# ----------------------------------------------------------------------- #
# §5 — behavioral assessment for hidden leaves (pure decision logic)       #
# ----------------------------------------------------------------------- #

_LEGACY_REDIRECT_HINTS = ("renamed", "moved", "deprecated", "use ")


def assess_hidden_leaf(
    full: str,
    rc: int,
    stderr: str,
    meta: dict | None,
) -> list:
    """Decide the §5 behavioral finding(s) for one hidden leaf.

    Pure function over ``(exit code, stderr, _deprecated_alias metadata)``
    so tests can exercise the phase ladder without subprocesses.

    - ``meta is None`` — legacy expectation: hidden leaves are Phase-E
      style redirects (non-zero exit + redirect hint on stderr).
    - ``phase == "warn"`` — Phase W forwards: MUST exit 0 AND print
      'deprecated' on stderr.
    - ``phase == "error"`` — Phase E: MUST exit 2.

    ``rc == -1`` (subprocess timeout / launch failure) yields no finding
    for metadata-bearing aliases — an unrunnable binary is not evidence
    about the ladder.
    """
    from ._audit import Violation

    if meta is None:
        if rc == 0:
            return [
                Violation(
                    full,
                    "§5",
                    "hidden leaf exited 0 — expected non-zero deprecation redirect",
                )
            ]
        if not any(tok in stderr.lower() for tok in _LEGACY_REDIRECT_HINTS):
            return [
                Violation(
                    full,
                    "§5",
                    "hidden leaf exited non-zero but stderr lacks redirect hint "
                    "(expected 'renamed', 'moved', 'deprecated', or 'use ...')",
                )
            ]
        return []

    if rc == -1:
        return []

    phase = str(meta.get("phase") or "")
    findings: list = []
    if phase == "warn":
        if rc != 0:
            findings.append(
                Violation(
                    full,
                    "§5",
                    f"warn-phase deprecated alias exited {rc} — Phase W "
                    f"aliases forward to the target and exit 0",
                )
            )
        if "deprecated" not in stderr.lower():
            findings.append(
                Violation(
                    full,
                    "§5",
                    "warn-phase deprecated alias printed no 'deprecated' "
                    "warning on stderr (once-per-shell doctrine message)",
                )
            )
        return findings
    if phase == "error":
        if rc != 2:
            findings.append(
                Violation(
                    full,
                    "§5",
                    f"error-phase deprecated alias exited {rc}, expected 2 "
                    f"(hard redirect per the deprecation ladder)",
                )
            )
        return findings
    findings.append(
        Violation(
            full,
            "§5",
            f"deprecated alias metadata has unknown phase {phase!r} "
            f"(expected 'warn' or 'error')",
        )
    )
    return findings
