"""Which TREE audit-cli reads `.scitex/dev/cli-audit-dict.yaml` out of.

The wrong-subject footgun, one layer deeper
-------------------------------------------
``ecosystem audit-all <pkg> --path <worktree>`` threads ``--path`` to all
six sub-auditors, and audit-cli's CLI already resolves its target tree
through the shared ``resolve_target_tree`` and prints the
``auditing <path> … via explicit`` banner. But the per-package CUSTOM
DICTIONARY (``.scitex/dev/cli-audit-dict.yaml`` — §1c nouns/verbs and the
§1f ``verb_exceptions:`` escape hatch) was resolved from
``Path.cwd()`` REGARDLESS of ``--path``.

So a caller who pinned a worktree got five sub-auditors grading that
worktree while audit-cli graded the worktree's SOURCE but the *cwd's*
dictionary — and a §1f violation whose fix (a new ``verb_exceptions:``
entry) lived only in the pinned tree kept firing. Reported by
scitex-storage against v0.38.1: the dict entry was well-formed; the
auditor was reading a different file. The run's own output looked
internally consistent, which is what made it cost minutes instead of
seconds.

The seam
--------
``use_dict_root(root, via)`` pins the tree for the duration of one audit;
every dictionary lookup goes through ``dict_candidate_paths()``, which
reads the pin (falling back to ``Path.cwd()``, labelled ``cwd``, when
nothing is pinned — the historical behaviour). It is a real value seam,
not a patch point: tests set it with the same public call the production
path uses.

Naming the subject
------------------
``surface_dict_source`` announces the resolved dictionary file(s) in the
same shape as the resolved-tree banner
(``<dist>: cli-audit dict <path> (<layer>, via <rule>; read|absent)``)
BEFORE any results. An auditor that names its own subject can be checked
against what the caller asked for; one that does not, cannot — storage
credited exactly that property with making both of their findings
findable.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .._emit import emit

#: Path of the custom dictionary relative to a repo (or home) root.
DICT_RELPATH = (".scitex", "dev", "cli-audit-dict.yaml")

_PINNED: ContextVar[tuple[Path, str] | None] = ContextVar(
    "scitex_dev_cli_audit_dict_root", default=None
)


@contextmanager
def use_dict_root(root: str | Path | None, via: str = "explicit"):
    """Pin the tree the project-layer custom dict is read from.

    ``root=None`` restores the unpinned (cwd) behaviour, so a caller can
    pass a possibly-``None`` resolved tree without branching. ``via``
    names the resolution rule (``explicit`` / ``cwd`` / ``registry`` —
    the vocabulary of ``.._target_tree.resolve_target_tree``) and is
    reported verbatim by :func:`dict_source_report`.
    """
    token = _PINNED.set(None if root is None else (Path(root), via))
    try:
        yield
    finally:
        _PINNED.reset(token)


def resolved_dict_root() -> tuple[Path, str]:
    """Return ``(root, via)`` for the project dictionary layer.

    The pinned tree when one is active, else the current working
    directory labelled ``cwd``. Fail-safe: an unlinked cwd degrades to
    the home directory rather than raising mid-audit.
    """
    pinned = _PINNED.get()
    if pinned is not None:
        return pinned
    try:
        return Path.cwd(), "cwd"
    except OSError:  # pragma: no cover — cwd unlinked underneath us
        return Path.home(), "cwd"


def _layers() -> list[tuple[Path, str, str]]:
    """``(path, layer, via)`` for each dict layer, project first, deduped.

    Deduplicated by resolved path — when the project root IS the home
    directory the two layers collapse to one file, which must be read
    once (a double read would double every missing-``# why`` finding).
    """
    root, via = resolved_dict_root()
    candidates = [
        (Path(root).joinpath(*DICT_RELPATH), "project", via),
        (Path.home().joinpath(*DICT_RELPATH), "user", "home"),
    ]
    out: list[tuple[Path, str, str]] = []
    seen: set[str] = set()
    for path, layer, layer_via in candidates:
        try:
            key = str(path.resolve())
        except OSError:  # pragma: no cover — defensive
            key = str(path)
        if key not in seen:
            seen.add(key)
            out.append((path, layer, layer_via))
    return out


def dict_candidate_paths() -> list[Path]:
    """The layered custom-dict locations, project layer first, deduped."""
    return [path for path, _layer, _via in _layers()]


def load_custom_dict() -> dict[str, set[str]]:
    """Merge the project + user custom dictionaries (§1c noun/verb tags).

    Extracted verbatim from `._audit._load_custom_dict`, which still
    re-exports it. The ONLY behavioural change is the source of the
    project layer: `dict_candidate_paths()` (pinned tree, else cwd)
    instead of `Path.cwd()` unconditionally.

    Layer precedence is unchanged: the list is walked in REVERSE so the
    user layer loads first and the project layer's tags are added on
    top.
    """
    import yaml

    out: dict[str, set[str]] = {}
    for path in reversed(dict_candidate_paths()):
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        for tag, key in [
            ("noun", "nouns"),
            ("verb-t", "transitive_verbs"),
            ("verb-i", "intransitive_verbs"),
        ]:
            for w in data.get(key, []) or []:
                out.setdefault(w.lower(), set()).add(tag)
    return out


def dict_source_report(distribution: str) -> list[str]:
    """One line per dictionary layer naming the file and how it was found.

    Deliberately reports ABSENT layers too: "no project dict was found
    at <path>" is the single most useful line when a dict entry appears
    to be ignored, and it is exactly the line that is missing when an
    auditor only reports what it did read.
    """
    lines: list[str] = []
    for path, layer, via in _layers():
        state = "read" if path.is_file() else "absent"
        lines.append(
            f"{distribution}: cli-audit dict {path} ({layer}, via {via}; {state})"
        )
    return lines


def surface_dict_source(distribution: str, json_out: bool = False) -> None:
    """Announce the resolved dictionary file(s) at INFO, before results.

    Human rail only: no-op under ``--json`` (same contract as the
    resolved-tree banner in ``.._project._resolved_tree``).
    """
    if json_out:
        return
    for line in dict_source_report(distribution):
        emit("info", line)


__all__ = [
    "DICT_RELPATH",
    "dict_candidate_paths",
    "dict_source_report",
    "load_custom_dict",
    "resolved_dict_root",
    "surface_dict_source",
    "use_dict_root",
]
