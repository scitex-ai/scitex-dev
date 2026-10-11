"""Project-audit plugin: package runtime state stays local to each host.

Shared configuration remains outside ``.scitex/<package>/runtime/``.
Every existing runtime directory must contain a catch-all ``.gitignore``;
exceptions after that catch-all and already-indexed runtime entries fail.
Runtime symlinks also need a parent ignore, since Git never reads ignore
files through a symlink. The auditor reads policies and index paths only,
never runtime payloads, and does not modify the audited tree.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_CODE = "PS-234"
_CATCH_ALL = frozenset({"*", "**", "/*", "/**", "**/*", "/**/*"})


def get_plugin() -> dict:
    """Provide the ecosystem-wide runtime-state rule and its checker."""
    return {
        "rules": [
            (
                _CODE,
                "§4b",
                "Every .scitex/<package>/runtime/ directory is host-local: "
                "its .gitignore must ignore everything, with no exceptions, "
                "and no runtime entries may remain in the Git index. "
                "Runtime symlinks must also be ignored by a parent policy. "
                "Keep shared, tracked configuration outside runtime/.",
                "E",
                "runtime-state-gitignored",
            )
        ],
        "checks": [check_runtime_gitignore],
        "registry_checks": [check_runtime_registry_gitignore],
    }


def _state_roots(repo: Path) -> list[Path]:
    roots = [repo / ".scitex", repo / "src" / ".scitex"]
    if repo.name == ".scitex":
        roots.insert(0, repo)
    return roots


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(name, None)
    env["GIT_DISCOVERY_ACROSS_FILESYSTEM"] = "1"
    try:
        return subprocess.run(
            ["git", "-c", "core.excludesFile=/dev/null", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"cannot inspect Git state: {type(exc).__name__}: {exc}") from exc


def _indexed_runtimes(repo: Path, roots: list[Path]) -> tuple[bool, dict[Path, list[str]]]:
    probe = _git(repo, "rev-parse", "--is-inside-work-tree")
    if probe.returncode:
        if "not a git repository" in probe.stderr:
            return False, {}
        raise RuntimeError(f"cannot inspect Git worktree: {probe.stderr.strip()}")
    if probe.stdout.strip() != "true":
        return False, {}
    specs = []
    prefixes = []
    for root in roots:
        prefix = root.relative_to(repo).as_posix()
        prefix = "" if prefix == "." else prefix + "/"
        prefixes.append(Path(prefix).parts)
        specs.extend((f":(glob){prefix}*/runtime", f":(glob){prefix}*/runtime/**"))
    result = _git(repo, "ls-files", "-z", "--", *specs)
    if result.returncode:
        raise RuntimeError(f"cannot inspect Git index: {result.stderr.strip()}")
    indexed: dict[Path, list[str]] = {}
    for name in filter(None, result.stdout.split("\0")):
        parts = Path(name).parts
        for prefix in prefixes:
            offset = len(prefix)
            if parts[:offset] != prefix or len(parts) < offset + 2:
                continue
            if parts[offset + 1] == "runtime":
                runtime = repo.joinpath(*parts[: offset + 2])
                indexed.setdefault(runtime, []).append(name)
                break
    return True, indexed


def _policy_problem(runtime: Path) -> str | None:
    if not runtime.is_dir():
        return "runtime/ is not an available directory; cannot verify its ignore policy."
    policy = runtime / ".gitignore"
    try:
        text = policy.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return f"cannot read runtime/.gitignore ({type(exc).__name__}); add a file containing `*`."
    covers_all = False
    for line in text.splitlines():
        # Git ignores unescaped trailing spaces, but leading spaces belong
        # to the pattern: ` *` does not cover every file.
        pattern = line.rstrip(" ")
        if pattern in _CATCH_ALL:
            covers_all = True
        elif pattern.startswith("!"):
            covers_all = False
    if not covers_all:
        return "runtime/.gitignore must contain a catch-all `*` with no later `!` exceptions."
    return None


def check_runtime_gitignore(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS-234 findings for every package state scope in this tree."""
    repo = Path(repo).absolute()
    _check_runtime_roots(repo, _state_roots(repo), violation_cls, out)


def check_runtime_registry_gitignore(
    scitex_dir: Path, violation_cls: type, out: list
) -> None:
    """Audit an explicit host registry once, including custom root names."""
    # Resolve the registry alias, which may point into a dotfiles checkout.
    # Preserve each runtime leaf symlink so Git checks the link's own path.
    root = Path(scitex_dir).resolve()
    _check_runtime_roots(root, [root], violation_cls, out)


def _check_runtime_roots(
    repo: Path, roots: list[Path], violation_cls: type, out: list
) -> None:
    """Check only the given scopes without consulting another host root."""
    runtimes: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for scope in root.iterdir():
                if scope.is_dir():
                    runtime = scope / "runtime"
                    if runtime.exists() or runtime.is_symlink():
                        runtimes.add(runtime)
        except OSError as exc:
            out.append(violation_cls(_CODE, str(root), f"cannot inspect state scopes: {exc}"))
    try:
        in_git, indexed = _indexed_runtimes(repo, roots)
    except RuntimeError as exc:
        if runtimes:
            out.append(violation_cls(_CODE, str(repo), str(exc)))
        return
    runtimes.update(indexed)
    for runtime in sorted(runtimes):
        problem = _policy_problem(runtime)
        if problem:
            out.append(violation_cls(_CODE, str(runtime / ".gitignore"), problem))
        if runtime in indexed:
            names = indexed[runtime]
            examples = ", ".join(names[:3])
            out.append(
                violation_cls(
                    _CODE,
                    str(runtime),
                    f"{len(names)} runtime entries are already tracked: {examples}. "
                    "Remove runtime entries from the Git index while retaining "
                    "local files; .gitignore does not untrack existing entries.",
                )
            )
        if runtime.is_symlink():
            ignored = (
                _git(repo, "check-ignore", "--no-index", "-q", "--", str(runtime))
                if in_git
                else None
            )
            if ignored is None or ignored.returncode:
                out.append(
                    violation_cls(
                        _CODE,
                        str(runtime),
                        "Runtime symlink must be excluded by a parent .gitignore "
                        "in an auditable Git worktree. Its target's .gitignore "
                        "cannot ignore the link itself.",
                    )
                )
