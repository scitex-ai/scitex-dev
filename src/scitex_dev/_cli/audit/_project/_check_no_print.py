# -*- coding: utf-8 -*-
"""PS-220 — `print(...)` in scitex package SOURCE (use scitex-logging).

Operator mandate: SciTeX code must NEVER emit human-facing messages with
the builtin `print`. A bare `print(...)` is invisible to the ecosystem's
structured, searchable, level-aware logging: it carries no level, no
aligned `INFO:` / `WARN:` / `ERRO:` / `SUCC:` prefix, no colour, and
cannot be filtered or silenced by a downstream consumer. The canonical
form is scitex-logging, with exactly FOUR levels::

    import scitex_logging as slogging
    log = slogging.getLogger(__name__)
    log.info("...")      # INFO:
    log.warning("...")   # WARN:
    log.error("...")     # ERRO:
    log.success("...")   # SUCC:

The aligned four-character prefixes are the point: they line the output
up in a column so a reader triages a log at a glance.

This rule statically AST-scans the importable package source tree
(`src/<pkg>/**.py`) and flags each `print(` call that is NOT provably
machine-readable stdout. It reads the source with `ast.parse` and never
imports the package, so it is safe to run against a broken tree.

What fires, and what is spared, is decided STRUCTURALLY by
:mod:`._print_discriminator` — see that module for the full rule. In
short: stderr always fires (scitex-logging owns stderr), prose to stdout
always fires, a serializer payload to stdout is spared, and anything
undecidable fires, because unknown must never read as safe.

Exemptions — a reason is MANDATORY
----------------------------------

A site the discriminator cannot clear opts out via a per-site entry in
`.scitex/dev/config.yaml`, following the `audit.capabilities` doctrine
(fixed scope + a visible notice) rather than the blanket `audit.skip`::

    audit:
      exemptions:
        PS-220:
          - path: src/pkg/_cli/_report.py
            line: 88
            reason: "renders the --json payload a shell consumes"

The exemption is pinned to ONE rule at ONE file:line, and an entry whose
`reason` is empty or whitespace-only is REJECTED — the site still fires,
and the rejection is itself reported as a violation. An exemption with no
stated reason is precisely the unexamined suppression this rule exists to
catch.

The legacy `# noqa` hatch still works for ONE release (see
`_LEGACY_NOQA_ENABLED`) but is DEPRECATED: it is a blanket, reasonless
flag that any unrelated `# noqa: E501` silences by accident, and it
leaves no auditable record of why. Sites carrying it now report as
`PS-220-noqa-deprecated` (severity W) so the fleet can migrate to
`audit.exemptions` without going red on promotion day.

Scope / exclusions
------------------

Only the *shippable* library source is graded — the tree that ends up in
the wheel and runs on a user's machine. `_src_files` walks `src/` only,
which already excludes repo-root `tests/`, `scripts/`, `examples/`, and
`docs/`; on top of that, any path component named `tests`, `scripts`,
`examples`, or `docs` (an in-package copy, e.g. `src/<pkg>/scripts/`) is
skipped too.

Severity — project-type aware
-----------------------------

E (error) for SciTeX ECOSYSTEM PACKAGES. Promoted from W on 2026-07-22 by
operator directive: the rule must ENFORCE the mandate, not leave it to
review. It shipped at W in its own rule tuple, and because the default
severity floor is `error`, its findings were not even PRINTED unless
someone passed `--severity warning` — a gate that could not fail. The
severity lives HERE, in the rule tuple, not in
`_registry._SEVERITY_OVERRIDES`.

The error severity is SCOPED. `resolve_ps220_severity` decides the
effective severity per project:

* ``project-type: [pip]`` (an ecosystem package) ⇒ **E**.
* ``project-type: [pip, research]`` (a hybrid) ⇒ **W**. The operator has
  NOT decided whether the logging mandate binds paper-producing research
  trees, so the conservative default surfaces the debt instead of wedging
  a publish on a decision nobody made.
* ``project-type: [research]`` alone ⇒ the rule never fires at all —
  `ProjectConfig.applies` admits ``PS-`` codes only for ``pip`` projects.
* ``audit.enforce-logging: error|warning|off`` overrides all of the
  above, so a repo can write the decision down explicitly.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._print_discriminator import should_flag

# Path components that mark a non-shippable subtree (an in-package copy of
# a dev-only area). Repo-root tests/scripts/examples/docs are already out
# of scope because `_src_files` walks `src/` only.
_EXCLUDED_PARTS = frozenset({"tests", "scripts", "examples", "docs"})

# Deprecated inline hatch. Kept working for ONE release so promoting PS-220
# to E does not red the whole fleet on the same day; every hit is reported as
# a W-severity deprecation notice pointing at `audit.exemptions`.
_LEGACY_NOQA_ENABLED = True


def _src_files(repo: Path) -> list[Path]:
    """Yield shippable .py files under `src/` (gitignore-naive, best-effort).

    Excludes `__pycache__` and any IN-PACKAGE `tests/`, `scripts/`,
    `examples/`, or `docs/` subtree (e.g. `src/<pkg>/examples/` — the
    scitex-scholar shape, which is most of that package's raw `print` count).
    Repo-root `tests/`, `scripts/`, `examples/`, `docs/` are already out of
    scope because this walks `src/` only.

    The exclusion is matched against the path RELATIVE TO `src/`, not the
    absolute path. Matching the absolute path was a latent way to silently
    disable the whole rule: a checkout living under any directory named
    `docs`, `tests`, `scripts`, or `examples` (say
    `~/scripts/scitex-io/src/scitex_io/_core.py`) made EVERY file match the
    exclusion, so the check reported a clean tree it had never looked at.
    That matters much more now that PS-220 is an error-level gate.
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


def _line_opts_out(lines: list[str], node: ast.AST) -> bool:
    """True iff any physical line spanned by `node` carries a `# noqa`.

    DEPRECATED — see the module docstring. This is a blanket, reasonless
    hatch: an unrelated `# noqa: E501` silences PS-220 by accident, and it
    records no reason anywhere an auditor can read.
    """
    start = getattr(node, "lineno", None)
    if start is None:
        return False
    end = getattr(node, "end_lineno", start) or start
    for lineno in range(start, end + 1):
        idx = lineno - 1
        if 0 <= idx < len(lines) and "noqa" in lines[idx]:
            return True
    return False


def _print_calls(text: str) -> tuple[ast.AST | None, list[ast.Call]]:
    """Return `(tree, every bare print(...) call node)` in `text`.

    A `print` call is an `ast.Call` whose `func` is the bare name `print`.
    Attribute forms (`x.print(...)`) are intentionally NOT matched — only
    the builtin is the target.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None, []
    hits: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "print":
            hits.append(node)
    return tree, hits


def _relative(py: Path, repo: Path) -> str:
    """POSIX path of `py` relative to `repo` (falls back to the full path)."""
    try:
        return py.relative_to(repo).as_posix()
    except ValueError:
        return py.as_posix()


_FIX_HINT = (
    "Use scitex-logging: `import scitex_logging as slogging; "
    "log = slogging.getLogger(__name__)` then `log.info(...)` / "
    "`log.warning(...)` / `log.error(...)` / `log.success(...)` for aligned "
    "`INFO:`/`WARN:`/`ERRO:`/`SUCC:` output. If this line legitimately emits "
    "machine-readable stdout that a consumer parses, declare a per-site "
    "exemption in `.scitex/dev/config.yaml` under `audit.exemptions: PS-220:` "
    "with a `path`, a `line`, and a MANDATORY `reason`."
)


def resolve_ps220_severity(config) -> str | None:
    """Resolve PS-220's effective severity for a project. None ⇒ do not fire.

    The no-bare-print mandate is an ERROR for SciTeX ECOSYSTEM PACKAGES. It is
    deliberately NOT an error for RESEARCH projects: the operator has not yet
    ruled on whether the logging mandate binds paper-producing trees, and the
    conservative default for an undecided question is to surface the debt
    (``W``) rather than to wedge a publish on a decision nobody made. Mirrors
    the established project-type severity branch for PA-306 under a ``django``
    project-type (`_cli/audit/_api/_audit.py:184-190`).

    Resolution order:

    1. Explicit ``audit.enforce-logging`` in ``.scitex/dev/config.yaml``
       (``error`` / ``warning`` / ``off``) always wins — the decision point is
       per-repo and written down.
    2. Otherwise ``research`` in ``project-type`` ⇒ ``W``.
    3. Otherwise ``E`` (the rule tuple's registered severity).

    Note a research-ONLY project never reaches this at all: PS-220 is a ``PS-``
    code, and `ProjectConfig.applies` (`_config/_loader.py:187-189`) admits
    ``PS-`` rules only when ``pip`` is among the project types, so the auditor
    drops the findings wholesale. This function is what governs the HYBRID
    ``project-type: [pip, research]`` repo, which is the case that would
    otherwise be silently promoted to an error.
    """
    explicit = getattr(config, "enforce_logging", None)
    if explicit == "off":
        return None
    if explicit == "warning":
        return "W"
    if explicit == "error":
        return "E"
    types = getattr(config, "project_types", frozenset()) or frozenset()
    if "research" in types:
        return "W"
    return "E"


def _emit(out: list, violation_cls, severity: str, rule: str, where: str, detail: str):
    """Append a violation, carrying a per-finding severity when it differs.

    `Violation.severity_override` is the auditor's established way to set a
    severity per finding rather than per rule (see `_violation.py:19-25` and
    `_new_vs_baseline.escalate_new_violations`). It is only set when it would
    actually change something, so the rule's registered severity stays the
    default story a reader gets.
    """
    v = violation_cls(rule, where, detail)
    if severity != "E":
        try:
            v.severity_override = severity
        except (AttributeError, TypeError):  # pragma: no cover - stub classes
            pass
    out.append(v)
    return v


def _report_rejected_exemptions(
    repo: Path, config, violation_cls, out: list, severity: str
) -> None:
    """Surface `audit.exemptions` entries that were rejected as malformed.

    A rejected entry exempts NOTHING (the site still fires). Reporting it
    separately is what keeps a blank-reason exemption from reading as a
    quiet no-op the author believes worked.
    """
    for notice in tuple(getattr(config, "exemption_errors", ()) or ()):
        if not notice.startswith("PS-220"):
            continue
        _emit(
            out,
            violation_cls,
            severity,
            "PS-220",
            str(repo / ".scitex/dev/config.yaml"),
            (
                f"Invalid `audit.exemptions` entry — {notice}. The entry "
                f"does NOT exempt anything; an exemption must state WHY "
                f"the site is exempt."
            ),
        )


def check_ps220_no_print(
    repo: Path,
    violation_cls: type,
    out: list,
    *,
    config=None,
) -> None:
    """Append PS-220 violations for `print(...)` calls in package source.

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
        the check honours `audit.exemptions` on its own; passing it in lets a
        caller that already loaded the config avoid a second read.
    """
    if config is None:
        try:
            from .._config import load_config

            config = load_config(repo)
        except Exception:  # pragma: no cover - config is best-effort here
            config = None

    severity = resolve_ps220_severity(config) if config is not None else "E"
    if severity is None:
        # `audit.enforce-logging: off` — the project has explicitly opted out.
        return

    if config is not None:
        _report_rejected_exemptions(repo, config, violation_cls, out, severity)

    exemption_for = getattr(config, "exemption_for", None)

    for py in _src_files(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tree, calls = _print_calls(text)
        if tree is None or not calls:
            continue
        lines = text.splitlines()
        rel = _relative(py, repo)
        for node in calls:
            flag, why = should_flag(tree, node)
            if not flag:
                continue
            line_no = getattr(node, "lineno", 0)

            if exemption_for is not None and exemption_for("PS-220", rel, line_no):
                continue

            if _LEGACY_NOQA_ENABLED and _line_opts_out(lines, node):
                # Always W — the deprecation notice must never be the thing
                # that reds a build; it exists to give the fleet a migration
                # window off the reasonless hatch.
                _emit(
                    out,
                    violation_cls,
                    "W",
                    "PS-220-noqa-deprecated",
                    f"{py}:{line_no}",
                    (
                        f"`print(...)` at line {line_no} is suppressed by a "
                        f"DEPRECATED bare `# noqa`. That hatch is blanket "
                        f"and reasonless — an unrelated `# noqa: E501` "
                        f"silences PS-220 by accident, and it records no "
                        f"auditable reason. It stops working next release. "
                        f"Migrate to `.scitex/dev/config.yaml` "
                        f"`audit.exemptions: PS-220:` with `path: {rel}`, "
                        f"`line: {line_no}`, and a written `reason`."
                    ),
                )
                continue

            _emit(
                out,
                violation_cls,
                severity,
                "PS-220",
                f"{py}:{line_no}",
                (
                    f"`print(...)` in package source (line {line_no}): "
                    f"{why}. {_FIX_HINT}"
                ),
            )


# Rule definition, CO-LOCATED with its check (same pattern as
# `_check_no_url_deps.URL_DEP_RULES` / `_check_version_flag.VERSION_FLAG_RULES`);
# `_registry.py` merges `PRINT_FORBIDDEN_RULES` on the same terms.
#
# Severity E (operator directive 2026-07-22). The severity lives HERE, in the
# rule tuple — NOT in `_registry._SEVERITY_OVERRIDES`. Both are honoured now
# that `_patch` runs after the co-located merges, but the co-located tuple is
# the rule's own home and is what a reader checks first.
#
# (code, section, message, severity, slug)
PRINT_FORBIDDEN_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-220",
        "§2",
        (
            "`print(...)` in scitex package source. SciTeX code must emit "
            "human-facing messages through scitex-logging, never the builtin "
            "`print`: `import scitex_logging as slogging; "
            "log = slogging.getLogger(__name__)` then `log.info(...)` / "
            "`log.warning(...)` / `log.error(...)` / `log.success(...)` for "
            "aligned, coloured, searchable `INFO:`/`WARN:`/`ERRO:`/`SUCC:` "
            "output. A bare `print` has no level, no prefix, and cannot be "
            "filtered by a downstream consumer. Machine-readable stdout (a "
            "`--json` payload, piped data) is spared STRUCTURALLY — a stdout "
            "`print` whose sole argument is a serializer call or a rendered "
            "payload variable does not fire — because scitex-logging writes to "
            "stderr and would corrupt it. Everything else, including any "
            "undecidable destination or payload, fires and needs a per-site "
            "`audit.exemptions` entry carrying a MANDATORY reason. Scope is "
            "the shippable `src/<pkg>/**.py` tree "
            "(tests/scripts/examples/docs excluded)."
        ),
        "E",
        "source-uses-print-not-scitex-logging",
    ),
    (
        "PS-220-noqa-deprecated",
        "§2",
        (
            "A PS-220 site is suppressed by the DEPRECATED bare `# noqa` "
            "hatch. That hatch is blanket and reasonless: an unrelated "
            "`# noqa: E501` silences PS-220 by accident, and it leaves no "
            "auditable record of WHY the site is exempt. Migrate to a per-site "
            "`.scitex/dev/config.yaml` `audit.exemptions: PS-220:` entry with "
            "`path`, `line`, and a written `reason`. The `# noqa` hatch is "
            "honoured for ONE more release, then removed."
        ),
        "W",
        "ps220-noqa-hatch-deprecated",
    ),
]


# EOF
