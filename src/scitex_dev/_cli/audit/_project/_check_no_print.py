# -*- coding: utf-8 -*-
"""PS-220 — no pure-print/status logging in shippable SciTeX source.

Operator mandate: SciTeX code must NEVER emit human-facing messages with
the builtin `print`, Rich ``Console.print``, or a stdlib logger. Such output is
invisible to the ecosystem's
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
(`src/<pkg>/**.py`) and flags builtin ``print`` calls that are not provably
data transport, Rich ``Console.print`` calls, and stdlib
``logging.getLogger`` acquisition. It reads source with :mod:`ast` and never
imports the package.

What fires, and what is spared, is decided STRUCTURALLY by
:mod:`._print_discriminator` — see that module for the full rule. In
short: stderr always fires (scitex-logging owns stderr), prose to stdout
always fires, a serializer payload to stdout is spared, and anything
undecidable fires, because unknown must never read as safe.

Only narrow, mechanically proved transports are spared: a recognized
serializer to stdout, a caller-owned required ``file=`` stream, or a direct
content parameter in an explicitly named rendering API. Configuration cannot
downgrade, disable, or manually exempt PS-220.

The legacy `# noqa` hatch is GONE (removed 2026-07-23). It was a blanket,
reasonless flag that any unrelated `# noqa: E501` silenced by accident, and
it left no auditable record of why. It was deprecated for one release with a
`PS-220-noqa-deprecated` notice; a sweep of all 118 repos under
`/home/ywatanabe/proj` at removal time (8956 `src/**.py` files, 4448 flagged
sites) found ZERO sites using it, with a planted-user control confirming the
sweep could see one. There is no per-site opt-out.

Scope / exclusions
------------------

Only the *shippable* library source is graded — the tree that ends up in
the wheel and runs on a user's machine. `_src_files` walks `src/` only,
which already excludes repo-root `tests/`, `scripts/`, `examples/`, and
`docs/`; on top of that, any path component named `tests`, `scripts`,
`examples`, or `docs` (an in-package copy, e.g. `src/<pkg>/scripts/`) is
skipped too.

PS-220 is an unconditional error-tier rule. The former staged
``audit.enforce-logging`` switch is intentionally ignored by the checker;
old ``warning`` and ``off`` declarations cannot weaken the gate.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from ._print_discriminator import should_flag

# Path components that mark a non-shippable subtree (an in-package copy of
# a dev-only area). Repo-root tests/scripts/examples/docs are already out
# of scope because `_src_files` walks `src/` only.
_EXCLUDED_PARTS = frozenset({"tests", "scripts", "examples", "docs"})

_DEFAULT_SEVERITY = "E"

# Legacy config parse errors remain errors; accepted legacy settings do not
# alter enforcement.
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


@dataclass(frozen=True)
class _OutputCall:
    """One forbidden output primitive discovered in source."""

    kind: str
    call: ast.Call


def _import_aliases(tree: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """Return stdlib logging modules/getters and Rich Console class names."""
    logging_modules: set[str] = set()
    logging_getters: set[str] = set()
    console_classes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "logging":
                    logging_modules.add(alias.asname or "logging")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "logging":
                logging_getters.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "getLogger"
                )
            elif node.module == "rich.console":
                console_classes.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "Console"
                )
    return logging_modules, logging_getters, console_classes


def _rich_console_instances(tree: ast.AST, class_names: set[str]) -> set[str]:
    """Return names assigned an imported Rich ``Console(...)`` instance."""
    instances = {"console"}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        constructor = value.func
        if not (isinstance(constructor, ast.Name) and constructor.id in class_names):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        instances.update(t.id for t in targets if isinstance(t, ast.Name))
    return instances


def _is_console_receiver(
    receiver: ast.AST, console_classes: set[str], instances: set[str]
) -> bool:
    if isinstance(receiver, ast.Name):
        return receiver.id in instances
    if isinstance(receiver, ast.Attribute):
        return receiver.attr == "console"
    if isinstance(receiver, ast.Call):
        return (
            isinstance(receiver.func, ast.Name) and receiver.func.id in console_classes
        )
    return False


def _output_calls(text: str) -> tuple[ast.AST | None, list[_OutputCall]]:
    """Return forbidden output calls, without importing the scanned module."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None, []
    logging_modules, logging_getters, console_classes = _import_aliases(tree)
    console_instances = _rich_console_instances(tree, console_classes)
    hits: list[_OutputCall] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "print":
            hits.append(_OutputCall("builtin print", node))
            continue
        if isinstance(func, ast.Name) and func.id in logging_getters:
            hits.append(_OutputCall("stdlib logging.getLogger", node))
            continue
        if not isinstance(func, ast.Attribute):
            continue
        if (
            func.attr == "getLogger"
            and isinstance(func.value, ast.Name)
            and func.value.id in logging_modules
        ):
            hits.append(_OutputCall("stdlib logging.getLogger", node))
        elif func.attr == "print" and _is_console_receiver(
            func.value, console_classes, console_instances
        ):
            hits.append(_OutputCall("Rich Console.print", node))
    return tree, hits


_FIX_HINT = (
    "Use scitex-logging: `import scitex_logging as slogging; "
    "log = slogging.getLogger(__name__)` then `log.info(...)` / "
    "`log.warning(...)` / `log.error(...)` / `log.success(...)` for aligned "
    "`INFO:`/`WARN:`/`ERRO:`/`SUCC:` output. Data transport must use a "
    "mechanically recognized serializer, explicit content-rendering contract, "
    "or caller-owned required stream; PS-220 has no configuration bypass."
)


def resolve_ps220_severity(config) -> str | None:
    """Return PS-220's unconditional error severity.

    ``config`` remains in the signature for API compatibility, but no project
    setting may downgrade or disable this ecosystem-wide logging tier.
    """
    del config
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
    """Surface malformed legacy configuration as error-tier findings."""
    from ._exemption_config_errors import report_exemption_config_errors

    report_exemption_config_errors(
        repo,
        config,
        "PS-220",
        lambda where, detail: _emit(
            out, violation_cls, _CONFIG_ERROR_SEVERITY, "PS-220", where, detail
        ),
    )
    explicit = getattr(config, "enforce_logging", None)
    if explicit is not None:
        _emit(
            out,
            violation_cls,
            _CONFIG_ERROR_SEVERITY,
            "PS-220",
            str(repo / ".scitex/dev/config.yaml"),
            (
                "`audit.enforce-logging` is retired: PS-220 is mandatory "
                "error tier and has no project-level severity switch. Remove "
                "the declaration."
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
                f"PS-220 remains at its mandatory severity "
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
    """Append PS-220 violations for forbidden output in package source.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing `src/`).
    violation_cls : type
        The auditor's `Violation` dataclass `(rule, where, detail)`.
    out : list
        Violations are appended in place (project-auditor convention).
    config : ProjectConfig, optional
        Pre-loaded project config. It cannot weaken PS-220; passing it avoids
        a second read and lets malformed legacy declarations be reported.
    """
    if config is None:
        try:
            from .._config import load_config

            config = load_config(repo)
        except Exception:  # pragma: no cover - config is best-effort here
            config = None

    severity = resolve_ps220_severity(config)

    if config is not None:
        _report_config_errors(repo, config, violation_cls, out)

    for py in _src_files(repo):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tree, calls = _output_calls(text)
        if tree is None or not calls:
            continue
        for site in calls:
            node = site.call
            if site.kind == "builtin print":
                flag, why = should_flag(tree, node)
                if not flag:
                    continue
            elif site.kind == "Rich Console.print":
                why = (
                    "renders human-facing output without the SciTeX logging "
                    "tier, so it has no ecosystem level or searchable record"
                )
            else:
                why = (
                    "constructs a stdlib logger; shippable SciTeX status and "
                    "diagnostic output must use `scitex_logging.getLogger`"
                )
            line_no = getattr(node, "lineno", 0)

            _emit(
                out,
                violation_cls,
                severity,
                "PS-220",
                f"{py}:{line_no}",
                (f"{site.kind} in package source (line {line_no}): {why}. {_FIX_HINT}"),
            )


# Rule definition, CO-LOCATED with its check (same pattern as
# `_check_no_url_deps.URL_DEP_RULES` / `_check_version_flag.VERSION_FLAG_RULES`);
# `_registry.py` merges `PRINT_FORBIDDEN_RULES` on the same terms.
#
# Severity E — ecosystem-wide and unconditional. Historical
# ``audit.enforce-logging`` declarations cannot downgrade or disable it.
#
# (code, section, message, severity, slug)
PRINT_FORBIDDEN_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-220",
        "§2",
        (
            "Human-facing output in SciTeX package source must use "
            "scitex-logging, never builtin `print`, Rich `Console.print`, or "
            "stdlib `logging.getLogger`: `import scitex_logging as slogging; "
            "log = slogging.getLogger(__name__)` then `log.info(...)` / "
            "`log.warning(...)` / `log.error(...)` / `log.success(...)` for "
            "aligned, coloured, searchable `INFO:`/`WARN:`/`ERRO:`/`SUCC:` "
            "output. A bare `print` has no level, no prefix, and cannot be "
            "filtered by a downstream consumer. Machine-readable stdout (a "
            "`--json` payload, piped data) is spared STRUCTURALLY when it is a "
            "recognized serializer, an explicit content-rendering contract, "
            "or a caller-owned required stream does not fire, because routing "
            "protocol output through stderr would corrupt it. Everything else "
            "fires; there is no staged opt-in or configuration bypass. Scope is "
            "the shippable `src/<pkg>/**.py` tree "
            "(tests/scripts/examples/docs excluded). Reported as an ERROR for "
            "every SciTeX package."
        ),
        _DEFAULT_SEVERITY,
        "source-uses-print-not-scitex-logging",
    ),
]


# EOF
