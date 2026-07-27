"""audit-cli `--path`-rooted static source scans (§2 / §11).

Companion to `_run._audit_one`. The command-tree walk in `_audit_one`
audits the INSTALLED console script (imported in-process) — that half is
inherently import-based and cannot be pointed at an arbitrary uninstalled
tree. But the two purely-static SOURCE scans, §2 (no interactive prompts)
and §11 (Click-not-argparse), read `.py` files off disk and CAN be rooted
at an explicit checkout.

The originals in `_audit.py` resolve that checkout via
`importlib.find_spec` → ecosystem-registry `local_path` — i.e. the
installed / `~/proj/<pkg>` tree, NOT a `--path` worktree. This module
provides `--path`-honouring variants rooted at the tree resolved by the
shared `resolve_target_tree`, so audit-cli honours `--path` uniformly
with the other five sub-auditors (operator directive 2026-07-21; the
audit-all wrong-tree footgun).

It lives as its own module because `_audit.py` is already far over the
repo file-size budget (~2 kLOC) and the size hook forbids editing it; the
scan bodies below intentionally MIRROR the `_check_no_interactive_prompts`
/ `_check_cli_framework` logic in `_audit.py` and reuse its shared marker
helpers so the two stay close. Unify them into one repo-root-parametrised
implementation when `_audit.py` is finally split.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ._audit import (
    Violation,
    _has_file_interactive_ok_marker,
    _line_or_above_has_interactive_ok,
)


def _pkg_root_under(repo_root: Path, distribution: str) -> Path | None:
    """`<repo_root>/src/<import_name>/` when it exists, else None."""
    cand = Path(repo_root) / "src" / distribution.replace("-", "_")
    return cand if cand.is_dir() else None


# §2 forbidden call table — MIRRORS `_audit._check_no_interactive_prompts`.
_FORBIDDEN = {
    ("click", "confirm"): "click.confirm() — use `--yes`/`-y` and refuse-without-yes instead",
    ("click", "prompt"): "click.prompt() — accept the value as a CLI option/flag instead",
    ("getpass", "getpass"): "getpass.getpass() — accept secret via env var or --password-file",
    ("getpass", "getuser"): None,  # informational, not a prompt — exempt
}
_FORBIDDEN_BARE = {"input"}  # builtin input()


def check_no_interactive_prompts_under(
    distribution: str, repo_root: Path, out: list[Violation]
) -> None:
    """§2 — CLI source under `repo_root` must not block on stdin.

    Repo-rooted mirror of `_audit._check_no_interactive_prompts`. Skips
    `tests/` / `examples/` / `docs/` and honours the same per-call
    (`# audit-cli: interactive-ok`) / per-file
    (`# audit-cli: file-interactive-ok`) opt-out markers.
    """
    pkg_root = _pkg_root_under(repo_root, distribution)
    if pkg_root is None:
        return
    for py in pkg_root.rglob("*.py"):
        if any(s in py.parts for s in ("__pycache__", "tests", "examples", "docs")):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError:
            continue
        if _has_file_interactive_ok_marker(text):
            continue
        lines = text.split("\n")
        rel = py.relative_to(pkg_root.parent)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                key = (f.value.id, f.attr)
                if key not in _FORBIDDEN:
                    continue
                msg = _FORBIDDEN[key]
                if msg is None:
                    continue
                if _line_or_above_has_interactive_ok(lines, node.lineno):
                    continue
                out.append(
                    Violation(
                        distribution,
                        "§2",
                        f"interactive prompt at {rel}:{node.lineno} — {msg}",
                    )
                )
            elif isinstance(f, ast.Name) and f.id in _FORBIDDEN_BARE:
                if _line_or_above_has_interactive_ok(lines, node.lineno):
                    continue
                out.append(
                    Violation(
                        distribution,
                        "§2",
                        f"interactive `input()` at {rel}:{node.lineno} — "
                        "CLIs must be non-interactive; accept value via "
                        "option/flag or fail with a clear error.",
                    )
                )


_ARGPARSE_RE = re.compile(
    r"^\s*(import\s+argparse|from\s+argparse\s+import)", re.MULTILINE
)


def _ep_value_under(repo_root: Path, distribution: str) -> str | None:
    """`[project.scripts][distribution]` from `<repo_root>/pyproject.toml`."""
    pyproject = Path(repo_root) / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        import tomllib
    except ImportError:  # pragma: no cover — 3.10 path
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return None
    try:
        with open(pyproject, "rb") as fh:
            meta = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    scripts = (meta.get("project") or {}).get("scripts") or {}
    value = scripts.get(distribution)
    return value if isinstance(value, str) else None


def check_cli_framework_under(
    distribution: str, repo_root: Path, out: list[Violation]
) -> None:
    """§11 — the CLI tree under `repo_root` must use Click, not argparse.

    Repo-rooted mirror of `_audit._check_cli_framework`. Resolves the
    entry-point module from `<repo_root>/pyproject.toml` and scans the
    entry file plus every `.py` under its `_cli/` subtree.
    """
    ep_value = _ep_value_under(repo_root, distribution)
    if ep_value is None:
        return
    pkg_root = _pkg_root_under(repo_root, distribution)
    if pkg_root is None:
        return
    # entry-point "module.path:object" → concrete .py under the repo tree.
    mod_name = ep_value.split(":", 1)[0]
    parts = mod_name.split(".")[1:]  # drop the top-level import name (== pkg_root)
    ep_file: Path | None = None
    if not parts:
        cand = pkg_root / "__init__.py"
        ep_file = cand if cand.is_file() else None
    else:
        sub = pkg_root
        for p in parts[:-1]:
            sub = sub / p
        pkg_init = sub / parts[-1] / "__init__.py"
        mod_py = sub / f"{parts[-1]}.py"
        ep_file = pkg_init if pkg_init.is_file() else (mod_py if mod_py.is_file() else None)
    if ep_file is None:
        return

    py_files = [ep_file]
    cli_subdir = ep_file.parent / "_cli"
    if cli_subdir.is_dir():
        py_files += [
            p for p in cli_subdir.rglob("*.py")
            if p != ep_file and "__pycache__" not in p.parts
        ]
    elif ep_file.parent.name == "_cli":
        py_files += [
            p for p in ep_file.parent.rglob("*.py")
            if p != ep_file and "__pycache__" not in p.parts
        ]

    offenders: list[str] = []
    for f in py_files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if _ARGPARSE_RE.search(text):
            offenders.append(str(f))
    if offenders:
        sample = ", ".join(offenders[:3])
        more = f" (+{len(offenders) - 3} more)" if len(offenders) > 3 else ""
        out.append(
            Violation(
                distribution,
                "§11",
                f"CLI uses `argparse` — Click is canonical (zero drift, "
                f"shared CategorizedGroup, --json/--help-recursive built-in). "
                f"Migrate: {sample}{more}",
            )
        )


def scan_repo_source(
    distribution: str, repo_root: Path, out: list[Violation]
) -> None:
    """Run every `--path`-rootable static source scan against `repo_root`.

    Currently §2 (no interactive prompts) and §11 (Click, not argparse) —
    the two audit-cli rules whose resolution is a pure on-disk source
    read. Appends to ``out`` in place.
    """
    check_no_interactive_prompts_under(distribution, repo_root, out)
    check_cli_framework_under(distribution, repo_root, out)


def surface_cli_tree(
    distribution: str,
    repo_root: Path | None,
    resolved_via: str | None,
    json_out: bool,
) -> None:
    """Announce the resolved checkout before results (the #392 banner).

    No-op when no tree was resolved. Reuses audit-project's banner so
    audit-cli surfaces the same ``auditing <path> (branch …, via …)`` line
    as the other five sub-auditors.
    """
    if repo_root is None:
        return
    from .._project._resolved_tree import resolved_context, surface_resolved_tree

    surface_resolved_tree(
        distribution, resolved_context(repo_root), json_out, via=resolved_via
    )


__all__ = [
    "check_cli_framework_under",
    "check_no_interactive_prompts_under",
    "scan_repo_source",
    "surface_cli_tree",
]
