"""Canonical fingerprint of the effective rule set and its findings on a corpus.

Rule ownership moves (an engine rule handed over to the leaf package whose
API it enforces — see ``_rules/_handover.py``) must not change what users
see. This module produces the evidence: run :func:`fingerprint_paths` on a
fixed corpus before and after the move, compare the two documents, and any
difference in a rule's metadata or in a single finding shows up.

What is compared (``rules`` + ``findings`` + ``corpus``):

- ``rules`` — every effective rule (engine + plugins, through ``lookup``),
  keyed by id: severity, category, message, suggestion, requires, scope.
  WHO declares a rule is deliberately NOT part of it; ownership is what a
  move changes. It is reported separately under ``owners``.
- ``findings`` — every issue ``lint_file`` reports for every corpus file,
  as ``[path, line, col, rule_id, severity, category, message]``, sorted.
  Sorted because two emitters reporting the same (severity, line) can
  interleave differently; the set of findings is the behaviour.
- ``corpus`` — sha256 of every linted file, so a "no difference" verdict
  cannot come from linting two different trees.

A file whose lint raises is recorded under ``errors`` (compared too), never
skipped: a provider failing to load is a behaviour change.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

__all__ = ["CORPUS_SUFFIXES", "diff_fingerprints", "fingerprint_paths"]

CORPUS_SUFFIXES = frozenset({".py", ".ipynb", ".md", ".rst"})
_SKIP_DIRS = frozenset(
    {".git", "__pycache__", ".venv", "venv", "node_modules", ".worktrees"}
)


def _iter_corpus(paths):
    for raw in paths:
        root = Path(raw)
        if root.is_file():
            if root.suffix.lower() in CORPUS_SUFFIXES:
                yield root
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in CORPUS_SUFFIXES:
                continue
            rel = path.relative_to(root).parts
            # Session output trees (`<script>_out/`) are produced by running
            # the corpus, not part of it.
            if any(p in _SKIP_DIRS or p.endswith("_out") for p in rel[:-1]):
                continue
            yield path


def _rule_record(rule) -> dict:
    return {
        "severity": rule.severity,
        "category": rule.category,
        "message": rule.message,
        "suggestion": rule.suggestion,
        "requires": rule.requires,
        "scope": getattr(rule, "scope", ""),
    }


def fingerprint_paths(paths) -> dict:
    """Lint every corpus file under *paths*; return the canonical fingerprint.

    Args:
        paths: files or directories. Directories are walked recursively for
            ``CORPUS_SUFFIXES`` files, skipping VCS/venv dirs and ``*_out``
            session output trees.

    Returns:
        ``{"rules", "owners", "findings", "errors", "corpus"}`` — see the
        module docstring. ``owners`` maps each plugin-declared rule id to
        its provider and is informational (excluded from
        :func:`diff_fingerprints`).
    """
    from ._dispatch import lint_file
    from ._plugin_loader import load_plugins
    from ._rules import ALL_RULES, lookup

    payload = load_plugins()
    rule_ids = sorted(set(ALL_RULES) | set(payload["rules"]))
    rules = {rid: _rule_record(lookup(rid)) for rid in rule_ids}
    owners = {rid: "engine" for rid in ALL_RULES}
    owners.update(payload.get("rule_owners", {}))

    findings, errors, corpus = [], [], {}
    for path in _iter_corpus(paths):
        key = str(path.resolve())
        corpus[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            issues = lint_file(key)
        except Exception as exc:  # recorded and compared, never skipped
            errors.append([key, f"{type(exc).__name__}: {exc}"])
            continue
        for issue in issues:
            findings.append(
                [
                    key,
                    issue.line,
                    issue.col,
                    issue.rule.id,
                    issue.rule.severity,
                    issue.rule.category,
                    issue.rule.message,
                ]
            )
    findings.sort()
    errors.sort()
    return {
        "rules": rules,
        "owners": owners,
        "findings": findings,
        "errors": errors,
        "corpus": corpus,
    }


def diff_fingerprints(before: dict, after: dict) -> dict:
    """Return the behaviour differences between two fingerprints.

    Compares ``rules``, ``findings``, ``errors`` and ``corpus``; ignores
    ``owners``. An empty dict means identical behaviour on the same corpus.
    """
    out = {}
    for key in ("rules", "corpus"):
        a, b = before.get(key, {}), after.get(key, {})
        changed = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        if changed:
            out[key] = changed
    for key in ("findings", "errors"):
        a = Counter(tuple(x) for x in before.get(key, []))
        b = Counter(tuple(x) for x in after.get(key, []))
        if a != b:
            out[key] = {
                "only_before": sorted((a - b).elements()),
                "only_after": sorted((b - a).elements()),
            }
    return out


# EOF
