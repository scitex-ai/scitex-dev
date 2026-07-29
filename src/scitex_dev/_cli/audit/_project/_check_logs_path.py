# -*- coding: utf-8 -*-
"""PS-223 — non-`runtime/` logs-path string literal in package source.

The convention (`_skills/general/02_package/15_cron-management.md`;
`jobs/_logsink.py`): a package's log files — and every other
high-cardinality regenerable write — live under the gitignored,
GPFS-redirectable ``runtime/`` layer::

    ~/.scitex/<pkg>/runtime/logs/<slug>.log      # canonical

never directly under the package's local-state root::

    ~/.scitex/<pkg>/logs/<slug>.log              # FORBIDDEN

PRs #367 + #433 migrated every managed cron/log write off the old
``~/.scitex/<pkg>/logs/`` location and onto ``runtime/logs/``. Nothing
MECHANICALLY prevented a future regression back to the forbidden path:
the directive lived only in prose (docstrings, comments, the skill), fully
disconnected from the code it governs. A source edit could reintroduce a
bare ``"~/.scitex/dev/logs/x.log"`` literal and no gate would notice. This
rule closes that gap.

What fires
----------

A STRING LITERAL in the shippable ``src/<pkg>/**.py`` tree whose value is a
logs path whose segment directly after ``<pkg>/`` is ``logs`` — i.e. it
matches ``.scitex/<pkg>/logs/`` (with or without a ``~`` / ``$HOME`` /
absolute prefix), rather than the correct ``.scitex/<pkg>/runtime/logs/``.
The auditor reads the source with ``ast.parse`` and never imports the
package, so it is safe to run against a broken tree.

The correct ``runtime/logs/`` form is the CONTROL ARM: because the segment
directly after ``<pkg>/`` there is ``runtime`` (not ``logs``), the pattern
cannot match it. ``test__check_logs_path.py`` pins this — a mutation that
makes the check flag every logs path must turn that test red.

What is spared — prose, not paths
---------------------------------

The rule grades EXECUTED path literals, never the prose that documents
them. Two structural guards, both necessary, keep it off documentation:

1. **Docstrings and bare string-statements are skipped.** A module /
   class / function docstring — and any bare ``ast.Expr`` whose value is a
   string constant — is prose, not an executed path, and is excluded by
   node identity. Comments never reach the AST at all, so they are spared
   for free.
2. **Only whitespace-free path tokens fire.** A real filesystem path is a
   single unbroken token — ``"~/.scitex/dev/logs/cron-x.log"`` contains no
   space. Prose that MENTIONS the path — a ``description=``/``help=`` help
   string, a job DESCRIPTION, a sentence in a help spec — is a full
   sentence and always carries whitespace. Firing only on whitespace-free
   values is what keeps the rule off ``status.py``'s
   ``"... back to the pre-cleanup `~/.scitex/dev/logs/` path ..."`` help
   text and off the two ci-runner job descriptions, which mention such
   paths purely as prose.

Deliberately NOT caught: a path ASSEMBLED from segments —
``Path(base) / "dev" / "logs" / name`` — where no single string literal
contains ``.scitex/<pkg>/logs``. That is a real regression vector, but it
is out of THIS rule's scope, which is string literals by construction; a
segment-join matcher is a much broader, false-positive-prone rule and is
not what this closes. Such sites are surfaced by review, not by PS-223.

Prior art — adjacent, NOT superseded
------------------------------------

* **PS-180** (`_check_runtime_separation.py`) governs whether
  ``src/<pkg>/runtime/`` is gitignored — a directory INSIDE the wheel.
* **PS-222** (`_check_config_layout.py`) governs the tracked/runtime split
  of ``.scitex/<pkg-short>/`` ON DISK.
  This rule governs a SOURCE STRING that names a logs path. The trees, the
  failure modes and the remedies differ; none supersedes another.

Severity — W, and deliberately so
---------------------------------

Flat ``severity = "W"``, matching how new path-convention rules bake in
(PS-222's own docstring documents the precedent: PS-220 was promoted to
``E`` ecosystem-wide in PR #406, 44 repos newly FAILED on 1856 findings,
and the operator restaged it to ``W`` the next day). A convention rule
landing red across the fleet buys nothing a visible warning does not, and
costs every repo's green build.

The severity lives in the rule tuple below, NOT in
`_registry._SEVERITY_OVERRIDES` — `_patch` is applied at the BOTTOM of
`_registry.py`, after co-located rule sets are merged, and an override
added for a co-located rule before that point is silently ignored
(`_registry.py:1173-1184`).

Exemptions — a reason is MANDATORY
----------------------------------

A site the rule flags but that is genuinely legitimate opts out via a
per-site entry in `.scitex/dev/config.yaml`, keyed by rule code, with a
MANDATORY written ``reason`` (the same contract as PS-220 / PS-222)::

    audit:
      exemptions:
        PS-223:
          - path: src/pkg/_legacy.py
            line: 42
            reason: "read-only fallback for pre-migration logs"

A blank or whitespace-only reason is REJECTED: the site still fires, AND
the rejection is itself reported at ``E`` (config errors are never staged).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# Path components that mark a non-shippable subtree (an in-package copy of a
# dev-only area). Repo-root tests/scripts/examples/docs are already out of
# scope because `_src_files` walks `src/` only. Mirrors PS-220.
_EXCLUDED_PARTS = frozenset({"tests", "scripts", "examples", "docs"})

# The registered severity of the rule tuple below. `_emit` only sets a
# per-finding override when the effective severity DIFFERS from this.
_DEFAULT_SEVERITY = "W"

# Config errors (a rejected `audit.exemptions` entry) are reported at E
# regardless of the rule's own severity — a malformed override must never
# read as a quiet no-op the author believes worked.
_CONFIG_ERROR_SEVERITY = "E"

# A logs path whose segment directly after `<pkg>/` is `logs` — i.e. the
# FORBIDDEN non-runtime form `.scitex/<pkg>/logs/...`. The correct form is
# `.scitex/<pkg>/runtime/logs/...`: there the segment after `<pkg>/` is
# `runtime`, so `[^/]+` (which cannot cross a slash) can never let the
# trailing `/logs` match it. `logs` must be a COMPLETE segment — followed by
# a `/` or the end of the string — so `logsdir` / `logs.old` do not match.
_LOGS_RE = re.compile(r"\.scitex/[^/]+/logs(?:/|$)")

_FIX_HINT = (
    "Package logs live under the gitignored, GPFS-redirectable `runtime/` "
    "layer — `~/.scitex/<pkg>/runtime/logs/<slug>.log`, never "
    "`~/.scitex/<pkg>/logs/`. Resolve the path through "
    "`scitex_dev.jobs._respawn.runtime_dir_for_package` (or the package's "
    "own runtime-dir helper) so it lands under `runtime/logs/`. See "
    "`_skills/general/02_package/15_cron-management.md` and "
    "`jobs/_logsink.py`. If this literal is a legitimate read-only fallback, "
    "declare a per-site `audit.exemptions` entry (PS-223) with a `path`, a "
    "`line`, and a MANDATORY `reason`."
)


def _src_files(repo: Path) -> list[Path]:
    """Yield shippable .py files under `src/` (best-effort). Mirrors PS-220.

    Excludes `__pycache__` and any IN-PACKAGE `tests/`, `scripts/`,
    `examples/`, or `docs/` subtree. The exclusion is matched against the
    path RELATIVE TO `src/`, not the absolute path, so a checkout living
    under a dir named `docs`/`tests`/... does not silently disable the rule.
    """
    src = repo / "src"
    if not src.is_dir():
        return []
    out: list[Path] = []
    for p in src.rglob("*.py"):
        try:
            rel_parts = set(p.relative_to(src).parts)
        except ValueError:  # pragma: no cover - rglob results are under src
            continue
        if "__pycache__" in rel_parts:
            continue
        if rel_parts & _EXCLUDED_PARTS:
            continue
        out.append(p)
    return out


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """Node ids of every string Constant that is a docstring / bare string.

    A docstring — and any bare string-expression statement — is an
    `ast.Expr` whose `.value` is a string `ast.Constant`. Such nodes are
    prose, never an executed path, and are excluded by identity so the rule
    grades only path literals that are actually USED (assigned, joined,
    passed as an argument).
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                ids.add(id(node.value))
    return ids


def _has_whitespace(value: str) -> bool:
    """True iff `value` contains any whitespace — prose, not a path token.

    A real filesystem path is a single unbroken token; a description /
    help string that merely MENTIONS a path is a sentence and carries
    spaces. Firing only on whitespace-free values keeps the rule off prose
    the docstring/comment guard alone would miss (a `description=` kwarg is
    neither a docstring nor a comment).
    """
    return any(ch.isspace() for ch in value)


def _relative(py: Path, repo: Path) -> str:
    """POSIX path of `py` relative to `repo` (falls back to the full path)."""
    try:
        return py.relative_to(repo).as_posix()
    except ValueError:
        return py.as_posix()


def _emit(out: list, violation_cls, severity: str, where: str, detail: str):
    """Append a PS-223 violation, carrying a per-finding severity override.

    `Violation.severity_override` is the auditor's established per-finding
    severity mechanism (`_violation.py:19-25`). It is set only when it would
    change something — i.e. when `severity` differs from the rule tuple's
    REGISTERED severity.
    """
    v = violation_cls("PS-223", where, detail)
    if severity != _DEFAULT_SEVERITY:
        try:
            v.severity_override = severity
        except (AttributeError, TypeError):  # pragma: no cover - stub classes
            pass
    out.append(v)
    return v


def _report_config_errors(repo: Path, config, violation_cls, out: list) -> None:
    """Surface rejected `audit.exemptions` entries for PS-223, at `E`.

    A rejected exemption exempts NOTHING — the site still fires. Reporting
    the rejection separately keeps a reasonless exemption from reading as a
    quiet pass the author believes worked.
    """
    from ._exemption_config_errors import report_exemption_config_errors

    report_exemption_config_errors(
        repo,
        config,
        "PS-223",
        lambda where, detail: _emit(
            out, violation_cls, _CONFIG_ERROR_SEVERITY, where, detail
        ),
    )


def check_ps223_logs_path(
    repo: Path,
    violation_cls: type,
    out: list,
    *,
    config=None,
) -> None:
    """Append PS-223 violations for non-`runtime/` logs-path string literals.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing `src/`).
    violation_cls : type
        The auditor's `Violation` dataclass `(rule, where, detail)`.
    out : list
        Violations are appended in place (project-auditor convention).
    config : ProjectConfig, optional
        Pre-loaded project config. When omitted it is loaded from `repo` so
        the check honours `audit.exemptions` on its own; passing it in lets
        a caller that already loaded the config avoid a second read.
    """
    if config is None:
        try:
            from .._config import load_config

            config = load_config(repo)
        except Exception:  # pragma: no cover - config is best-effort here
            config = None

    if config is not None:
        _report_config_errors(repo, config, violation_cls, out)

    exemption_for = getattr(config, "exemption_for", None)

    for py in _src_files(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        doc_ids = _docstring_constant_ids(tree)
        rel = _relative(py, repo)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            value = node.value
            if not isinstance(value, str):
                continue
            if id(node) in doc_ids:
                continue
            if _has_whitespace(value):
                continue
            if not _LOGS_RE.search(value):
                continue

            line_no = getattr(node, "lineno", 0)
            if exemption_for is not None and exemption_for("PS-223", rel, line_no):
                continue

            _emit(
                out,
                violation_cls,
                _DEFAULT_SEVERITY,
                f"{py}:{line_no}",
                (
                    f"non-`runtime/` logs-path literal `{value}` (line "
                    f"{line_no}): the segment directly after `<pkg>/` is "
                    f"`logs`, not `runtime/logs`. {_FIX_HINT}"
                ),
            )


# Rule definition, CO-LOCATED with its check (same pattern as PS-222's
# `CONFIG_LAYOUT_RULES` / PS-220's `PRINT_FORBIDDEN_RULES`). `_registry.py`
# merges `LOGS_PATH_RULES` on identical terms, at the BOTTOM of the module —
# the severity below is the one that ships, because `_SEVERITY_OVERRIDES`
# cannot reach a co-located rule (see `_registry.py:1173-1184`).
#
# Severity W (warning): a path-convention rule landing red across the fleet
# buys nothing a visible warning does not — the PS-220 lesson (promoted to E
# in PR #406, 44 repos newly failing, restaged to W the next day).
#
# (code, section, message, severity, slug)
LOGS_PATH_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-223",
        "§2",
        (
            "non-`runtime/` logs-path string literal in package source. "
            "Package logs (and every high-cardinality regenerable write) "
            "live under the gitignored `runtime/` layer — "
            "`~/.scitex/<pkg>/runtime/logs/<slug>.log`, never directly under "
            "the package root at `~/.scitex/<pkg>/logs/`. PRs #367/#433 "
            "migrated every managed cron/log write onto `runtime/logs/`; this "
            "rule mechanically prevents a regression back to the forbidden "
            "path, which previously lived only in a docstring disconnected "
            "from the code. Flags a STRING LITERAL matching "
            "`.scitex/<pkg>/logs/` (the segment after `<pkg>/` is `logs`, "
            "not `runtime/logs`). Prose is spared structurally: docstrings, "
            "comments and whitespace-bearing description/help strings never "
            "fire — only whitespace-free path tokens do. Fix: resolve the "
            "path through `runtime_dir_for_package` so it lands under "
            "`runtime/logs/`. See "
            "`_skills/general/02_package/15_cron-management.md`. W during "
            "bake-in; opt out only via `audit.exemptions` with a reason."
        ),
        _DEFAULT_SEVERITY,
        "non-runtime-logs-path",
    ),
]


# EOF
