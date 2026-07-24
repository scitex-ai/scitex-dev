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

The legacy `# noqa` hatch is GONE (removed 2026-07-23). It was a blanket,
reasonless flag that any unrelated `# noqa: E501` silenced by accident, and
it left no auditable record of why. It was deprecated for one release with a
`PS-220-noqa-deprecated` notice; a sweep of all 118 repos under
`/home/ywatanabe/proj` at removal time (8956 `src/**.py` files, 4448 flagged
sites) found ZERO sites using it, with a planted-user control confirming the
sweep could see one. `audit.exemptions` is the only per-site opt-out.

Scope / exclusions
------------------

Only the *shippable* library source is graded — the tree that ends up in
the wheel and runs on a user's machine. `_src_files` walks `src/` only,
which already excludes repo-root `tests/`, `scripts/`, `examples/`, and
`docs/`; on top of that, any path component named `tests`, `scripts`,
`examples`, or `docs` (an in-package copy, e.g. `src/<pkg>/scripts/`) is
skipped too.

Severity — a STAGED rollout, opt-in per package
-----------------------------------------------

**W (warning) by default, for every project type.** The rule was promoted
to E ecosystem-wide on 2026-07-22 (PR #406); the measured blast radius —
44 repos newly FAILING on 1856 findings, top-5 repos carrying 64 % of them
(`GITIGNORED/ps220-blast-radius-20260722.md`) — is why the operator restaged
it on 2026-07-23 (Telegram 1691/1692)::

    「print に関しては順次やっていきましょうか。
      とりあえず warning で、移行できたものから red で」
    「red というか、エラー判定ってことですね」

This is a staged rollout, NOT a retreat: the findings stay fully visible on
every audit run, and each package promotes ITSELF to error the moment its
migration lands. The severity lives HERE, in the rule tuple, not in
`_registry._SEVERITY_OVERRIDES`.

`resolve_ps220_severity` decides the effective severity per project:

* ``audit.enforce-logging`` (see `_config._enforce_logging`) wins whenever
  it was ACCEPTED — this is the per-package opt-in::

      audit:
        enforce-logging:
          level: error
          reason: "print migration complete (PR #412)"

  ``error`` and ``off`` deviate from the default and so carry a MANDATORY
  written reason; a bare ``enforce-logging: error`` is rejected. ``warning``
  is accepted bare, because it is the default and changes nothing.
* Otherwise ⇒ **W**, for ``[pip]`` and ``[pip, research]`` alike.
* ``project-type: [research]`` alone ⇒ the rule never fires at all —
  `ProjectConfig.applies` admits ``PS-`` codes only for ``pip`` projects.

Config errors are NOT staged
----------------------------

A rejected `audit.exemptions` entry or a rejected `audit.enforce-logging`
declaration is reported at **E**, regardless of the project's staged PS-220
severity. The staging is about MIGRATION DEBT — a real print that has not
been converted yet. A malformed override is not debt; it is a config error,
and the whole point of the mandatory-reason design is that it must never
read as a quiet no-op the author believes worked.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._print_discriminator import should_flag

# Path components that mark a non-shippable subtree (an in-package copy of
# a dev-only area). Repo-root tests/scripts/examples/docs are already out
# of scope because `_src_files` walks `src/` only.
_EXCLUDED_PARTS = frozenset({"tests", "scripts", "examples", "docs"})

# PS-220's staged default severity — see the module docstring. Kept as a
# named constant because `_emit` needs to know which severity is the rule
# tuple's REGISTERED one (a per-finding override is only worth setting when
# it would actually change something).
_DEFAULT_SEVERITY = "W"

# Config errors (a rejected exemption entry, a rejected enforce-logging
# declaration) are reported at E regardless of the project's staged PS-220
# severity. Staging covers migration debt, not malformed config.
_CONFIG_ERROR_SEVERITY = "E"


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

    PS-220 is a STAGED rollout (operator directive 2026-07-23): the default is
    ``W`` for EVERY project type, and a package opts IN to ``E`` once it has
    finished migrating its prints to scitex-logging. See the module docstring
    for the directive and the blast-radius measurement behind it.

    Resolution order:

    1. An ACCEPTED ``audit.enforce-logging`` declaration in
       ``.scitex/dev/config.yaml`` wins — this is the per-package opt-in.
       ``error`` / ``off`` require a written reason and are parsed by
       `_config._enforce_logging.parse_enforce_logging`; a REJECTED
       declaration never reaches here (the loader leaves ``enforce_logging``
       None), so a reasonless opt-in cannot enforce anything.
    2. Otherwise ``W`` — the staged default, for ``[pip]`` and
       ``[pip, research]`` alike.

    Note a research-ONLY project never reaches this at all: PS-220 is a ``PS-``
    code, and `ProjectConfig.applies` admits ``PS-`` rules only when ``pip`` is
    among the project types, so the auditor drops the findings wholesale.
    """
    explicit = getattr(config, "enforce_logging", None)
    if explicit == "off":
        return None
    if explicit == "error":
        return "E"
    if explicit == "warning":
        return _DEFAULT_SEVERITY
    return _DEFAULT_SEVERITY


def _emit(out: list, violation_cls, severity: str, rule: str, where: str, detail: str):
    """Append a violation, carrying a per-finding severity when it differs.

    `Violation.severity_override` is the auditor's established way to set a
    severity per finding rather than per rule (see `_violation.py:19-25` and
    `_new_vs_baseline.escalate_new_violations`). It is only set when it would
    actually change something — i.e. when `severity` differs from the rule
    tuple's REGISTERED severity — so the rule's registered severity stays the
    default story a reader gets.
    """
    v = violation_cls(rule, where, detail)
    if severity != _DEFAULT_SEVERITY:
        try:
            v.severity_override = severity
        except (AttributeError, TypeError):  # pragma: no cover - stub classes
            pass
    out.append(v)
    return v


def _report_config_errors(repo: Path, config, violation_cls, out: list) -> None:
    """Surface rejected `audit.exemptions` / `audit.enforce-logging` entries.

    A rejected exemption exempts NOTHING (the site still fires); a rejected
    enforce-logging declaration enforces and silences NOTHING (the project
    falls back to the staged default). Reporting each one separately, at
    ``E``, is what keeps a reasonless override from reading as a quiet no-op
    the author believes worked — which is the entire point of demanding a
    written reason in the first place.
    """
    for notice in tuple(getattr(config, "exemption_errors", ()) or ()):
        if not notice.startswith("PS-220"):
            continue
        _emit(
            out,
            violation_cls,
            _CONFIG_ERROR_SEVERITY,
            "PS-220",
            str(repo / ".scitex/dev/config.yaml"),
            (
                f"Invalid `audit.exemptions` entry — {notice}. The entry "
                f"does NOT exempt anything; an exemption must state WHY "
                f"the site is exempt."
            ),
        )
    for notice in tuple(getattr(config, "enforce_logging_errors", ()) or ()):
        _emit(
            out,
            violation_cls,
            _CONFIG_ERROR_SEVERITY,
            "PS-220",
            str(repo / ".scitex/dev/config.yaml"),
            (
                f"Invalid `audit.enforce-logging` declaration — {notice} "
                f"PS-220 stays at its staged default severity "
                f"({_DEFAULT_SEVERITY}) for this project."
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

    severity = (
        resolve_ps220_severity(config) if config is not None else _DEFAULT_SEVERITY
    )
    if severity is None:
        # `audit.enforce-logging: off` — the project has explicitly opted out.
        return

    if config is not None:
        _report_config_errors(repo, config, violation_cls, out)

    exemption_for = getattr(config, "exemption_for", None)

    for py in _src_files(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tree, calls = _print_calls(text)
        if tree is None or not calls:
            continue
        rel = _relative(py, repo)
        for node in calls:
            flag, why = should_flag(tree, node)
            if not flag:
                continue
            line_no = getattr(node, "lineno", 0)

            if exemption_for is not None and exemption_for("PS-220", rel, line_no):
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
# Severity W — the STAGED-ROLLOUT default (operator directive 2026-07-23; it
# was briefly E ecosystem-wide in 0.35.0 / PR #406). A package promotes ITSELF
# to E via `audit.enforce-logging` once its print migration lands; see
# `resolve_ps220_severity` and `_config._enforce_logging`. The severity lives
# HERE, in the rule tuple — NOT in `_registry._SEVERITY_OVERRIDES`. Both are
# honoured now that `_patch` runs after the co-located merges, but the
# co-located tuple is the rule's own home and is what a reader checks first.
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
            "(tests/scripts/examples/docs excluded). Reported as a WARNING by "
            "default: the rollout is staged, and a package opts IN to an "
            "error-level gate once its migration is done, by declaring "
            "`audit.enforce-logging: {level: error, reason: \"...\"}` in "
            "`.scitex/dev/config.yaml`."
        ),
        _DEFAULT_SEVERITY,
        "source-uses-print-not-scitex-logging",
    ),
]


# EOF
