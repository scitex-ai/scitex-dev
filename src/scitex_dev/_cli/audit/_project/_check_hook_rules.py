#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/audit/_project/_check_hook_rules.py
"""PS-HOOK-010/011/012 — a package's agent guardrails must be DECLARED.

CONVENTION
----------
An agent guardrail (a Claude Code ``PreToolUse`` hook and friends) is
FEDERATED, not deployed by hand: the owning package declares a
``scitex_dev.hooks.HookRule`` and registers a provider under the
``scitex_dev.hooks`` entry-point group, and scitex-dev aggregates the corpus
(``scitex-dev ecosystem dev hooks``).

The declaration is what makes the ruleset reviewable. Before it existed, a
rule lived only inside its shell implementation: to learn what was enforced
and why, you read ~68 shell scripts. Measured 2026-08-12 on a live fleet
container, that opacity had already produced three distinct trees of "the
rules" -- the dotfiles-tracked copy, sac's ``to_home`` baseline, and the live
container copy -- with 15 scripts diverged between them and two enforcing
rules present in no git history at all. Nobody could audit a ruleset nobody
could enumerate.

WHAT FIRES
----------
``PS-HOOK-010`` (W)
    The repo ships agent-hook SCRIPTS but declares no ``HookRule`` anywhere
    and registers no ``scitex_dev.hooks`` entry point. The guardrails exist
    and enforce, but the corpus cannot see them.

``PS-HOOK-011`` (E)
    A ``HookRule(...)`` binds ``script=`` or ``predicate=`` to a path that
    does not exist in the repo. A declaration bound to nothing is a gate that
    cannot fire -- the failure mode this rule family exists to prevent, so it
    is an error rather than a warning.

``PS-HOOK-012`` (W)
    A ``HookRule(...)`` carries a ``reason=`` with no substance -- empty after
    the constructor's own check, a bare placeholder, or too short to state
    anything. The constructor already refuses an EMPTY reason; this catches
    the reason that is present but says nothing, which is the same opacity
    wearing a declaration.

WHAT IS SPARED
--------------
* Git hooks. ``src/<pkg>/_hooks/`` and ``.githooks/`` are the pre-push / lint
  / testmon runners, a different domain governed by PS-HOOK-001. They are
  never agent guardrails and never fire PS-HOOK-010.
* Repos that ship no agent hooks at all -- the overwhelming majority. This
  family is silent unless a package is in the guardrail business.
* Non-literal bindings. A ``script=`` built at runtime from a variable is not
  resolvable statically, so PS-HOOK-011 skips it rather than guessing.

PRIOR ART
---------
Mirrors ``_check_logs_path`` (PS-223) in structure: co-located rule tuples,
``_emit`` with per-finding severity, exemptions through
``config.exemption_for``.

EXEMPTION SCHEMA
----------------
Per-site, in ``.scitex/dev/config.yaml``::

    audit:
      exemptions:
        PS-HOOK-011:
          - path: src/pkg/_hook_rules.py
            line: 42
            reason: "script ships from the sibling deploy repo, tracked in #123"
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

#: PS-HOOK-011 is an ERROR: a binding that points at nothing enforces nothing,
#: and that is precisely the defect this family exists to catch. PS-HOOK-010
#: and -012 are warnings -- they flag opacity, which is bad but not broken.
_UNDECLARED_SEVERITY = "W"
_DANGLING_SEVERITY = "E"
_THIN_REASON_SEVERITY = "W"
_CONFIG_ERROR_SEVERITY = "E"

#: A reason shorter than this cannot state an incident, a directive or a
#: rationale. Chosen to admit a terse real reason ("He reads on a phone and a
#: bare number tells him nothing") and reject a gesture ("legacy", "TODO").
_MIN_REASON_CHARS = 30

#: Reasons that are present but empty of content.
_PLACEHOLDER_RE = re.compile(
    r"^\s*(todo|tbd|n/?a|none|because|legacy|historical|why not|see above|"
    r"self[- ]explanatory|obvious)\b\W*$",
    re.IGNORECASE,
)

#: Directories whose shell scripts are GIT hooks, not agent guardrails.
_GIT_HOOK_DIR_NAMES = frozenset({"_hooks", ".githooks", "hooks.d"})

#: Where a package conventionally ships agent-hook scripts.
_AGENT_HOOK_DIR_NAMES = frozenset(
    {
        "pre-tool-use",
        "post-tool-use",
        "user-prompt-submit",
        "session-start",
        "agent_hooks",
        "telegram_hooks",
    }
)


def _emit(out: list, violation_cls, code: str, severity: str, where: str, detail: str):
    """Append one finding, promoting severity when it differs from the rule's."""
    v = violation_cls(code, where, detail)
    default = {
        "PS-HOOK-010": _UNDECLARED_SEVERITY,
        "PS-HOOK-011": _DANGLING_SEVERITY,
        "PS-HOOK-012": _THIN_REASON_SEVERITY,
    }[code]
    if severity != default:
        try:
            v.severity_override = severity
        except (AttributeError, TypeError):  # pragma: no cover - stub classes
            pass
    out.append(v)
    return v


def _report_config_errors(repo: Path, config, violation_cls, out: list) -> None:
    """Surface rejected `audit.exemptions` entries for this family, at `E`.

    A rejected exemption exempts NOTHING -- the site still fires. Reporting
    the rejection separately keeps a reasonless exemption from reading as a
    quiet pass the author believes worked.
    """
    from ._exemption_config_errors import report_exemption_config_errors

    for code in ("PS-HOOK-010", "PS-HOOK-011", "PS-HOOK-012"):
        report_exemption_config_errors(
            repo,
            config,
            code,
            lambda where, detail, _c=code: _emit(
                out, violation_cls, _c, _CONFIG_ERROR_SEVERITY, where, detail
            ),
        )


def _iter_python_sources(repo: Path):
    """Yield the repo's own python sources, skipping vendored/venv trees."""
    src = repo / "src"
    root = src if src.is_dir() else repo
    for path in root.rglob("*.py"):
        parts = set(path.parts)
        if parts & {".venv", "venv", "site-packages", "build", ".tox", ".git"}:
            continue
        yield path


def _agent_hook_scripts(repo: Path) -> list[Path]:
    """Shell scripts that look like AGENT hooks, excluding git-hook trees."""
    found: list[Path] = []
    for path in repo.rglob("*.sh"):
        parts = set(path.parts)
        if parts & {".venv", "venv", "site-packages", "build", ".git", ".worktrees"}:
            continue
        if parts & _GIT_HOOK_DIR_NAMES:
            continue
        if parts & _AGENT_HOOK_DIR_NAMES:
            found.append(path)
    return found


def _const_str(node) -> str | None:
    """Return the literal str value of ``node``, or None if not a literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # Implicit concatenation across lines arrives as a JoinedStr-free BinOp
    # only when the author used `+`; adjacent literals are already folded.
    return None


def _hook_rule_calls(tree: ast.AST):
    """Yield every ``HookRule(...)`` call node in ``tree``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == "HookRule":
            yield node


def _kwargs_of(call: ast.Call) -> dict:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg}


def _resolve_binding(repo: Path, py_path: Path, value: str) -> bool:
    """Whether a declared script/predicate path resolves to a real file.

    Tried in order: relative to the declaring module's directory (the
    ship-beside-the-shim layout), relative to the package root, then relative
    to the repo root. Any hit counts -- the auditor's job is to catch a
    binding that resolves NOWHERE, not to police which layout was used.
    """
    candidates = [
        py_path.parent / value,
        repo / "src" / value,
        repo / value,
    ]
    pkg_dir = py_path.parent
    while pkg_dir != repo and pkg_dir.parent != pkg_dir:
        candidates.append(pkg_dir / value)
        pkg_dir = pkg_dir.parent
    return any(c.exists() for c in candidates)


def _declares_entry_point(repo: Path) -> bool:
    """Whether pyproject registers a ``scitex_dev.hooks`` provider."""
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        text = pyproject.read_text(encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover - unreadable file
        return False
    return 'entry-points."scitex_dev.hooks"' in text


def check_hook_rules(
    repo: Path,
    violation_cls: type,
    out: list,
    *,
    config=None,
) -> None:
    """Append PS-HOOK-010/011/012 findings for undeclared or broken guardrails."""
    exemption_for = getattr(config, "exemption_for", None) if config else None
    _report_config_errors(repo, config, violation_cls, out)

    any_declaration = False

    for py_path in _iter_python_sources(repo):
        try:
            text = py_path.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover - unreadable file
            continue
        if "HookRule(" not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:  # pragma: no cover - not this rule's business
            continue

        rel = str(py_path.relative_to(repo))
        for call in _hook_rule_calls(tree):
            any_declaration = True
            kwargs = _kwargs_of(call)
            line = getattr(call, "lineno", 0)
            rule_id = _const_str(kwargs.get("id")) or "<unknown>"

            # --- PS-HOOK-011: a binding that resolves nowhere ---------------
            for field in ("script", "predicate"):
                node = kwargs.get(field)
                if node is None:
                    continue
                value = _const_str(node)
                if value is None:
                    continue  # built at runtime; not statically resolvable
                if _resolve_binding(repo, py_path, value):
                    continue
                if exemption_for is not None and exemption_for(
                    "PS-HOOK-011", rel, line
                ):
                    continue
                _emit(
                    out,
                    violation_cls,
                    "PS-HOOK-011",
                    _DANGLING_SEVERITY,
                    f"{rel}:{line}",
                    (
                        f"HookRule({rule_id!r}).{field} points at {value!r}, "
                        f"which does not exist in this repo -- the rule is "
                        f"declared but bound to nothing, so it enforces nothing."
                    ),
                )

            # --- PS-HOOK-012: a reason with no substance --------------------
            reason = _const_str(kwargs.get("reason"))
            if reason is None:
                continue
            stripped = reason.strip()
            thin = len(stripped) < _MIN_REASON_CHARS or _PLACEHOLDER_RE.match(stripped)
            if not thin:
                continue
            if exemption_for is not None and exemption_for("PS-HOOK-012", rel, line):
                continue
            _emit(
                out,
                violation_cls,
                "PS-HOOK-012",
                _THIN_REASON_SEVERITY,
                f"{rel}:{line}",
                (
                    f"HookRule({rule_id!r}).reason is {stripped!r}, which does "
                    f"not state why the rule exists. A guardrail whose reason "
                    f"nobody can state is a guardrail nobody can retire."
                ),
            )

    # --- PS-HOOK-010: scripts enforce, but nothing declares them ------------
    if any_declaration or _declares_entry_point(repo):
        return
    scripts = _agent_hook_scripts(repo)
    if not scripts:
        return
    if exemption_for is not None and exemption_for("PS-HOOK-010", "pyproject.toml", 0):
        return
    shown = ", ".join(sorted(str(p.relative_to(repo)) for p in scripts)[:3])
    _emit(
        out,
        violation_cls,
        "PS-HOOK-010",
        _UNDECLARED_SEVERITY,
        "pyproject.toml",
        (
            f"{len(scripts)} agent-hook script(s) ship here ({shown}"
            f"{', …' if len(scripts) > 3 else ''}) but no HookRule declares "
            f"them and no `scitex_dev.hooks` entry point is registered -- the "
            f"rules enforce but cannot be enumerated, reviewed or audited."
        ),
    )


HOOK_RULES_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-HOOK-010",
        "§13",
        (
            "agent-hook scripts ship without any HookRule declaration or "
            "`scitex_dev.hooks` entry point (the guardrails enforce but "
            "cannot be enumerated or audited)"
        ),
        _UNDECLARED_SEVERITY,
        "hook-rules-undeclared",
    ),
    (
        "PS-HOOK-011",
        "§13",
        (
            "HookRule binds `script`/`predicate` to a path that does not "
            "exist in the repo (a declared gate that cannot fire)"
        ),
        _DANGLING_SEVERITY,
        "hook-rule-binding-dangling",
    ),
    (
        "PS-HOOK-012",
        "§13",
        (
            "HookRule carries a `reason` with no substance -- a placeholder "
            "or too short to state why the rule exists"
        ),
        _THIN_REASON_SEVERITY,
        "hook-rule-reason-thin",
    ),
]

__all__ = ["check_hook_rules", "HOOK_RULES_RULES"]
