"""Ecosystem-wide git operations: clone, checkout, pull.

Backs `scitex-dev ecosystem {clone, checkout, pull}` — bootstrap a
fresh machine and keep it in sync with `develop` across every repo.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from ._core import ECOSYSTEM


def _ssh_url(github_repo: str) -> str:
    return f"git@github.com:{github_repo}.git"


def _https_url(github_repo: str) -> str:
    return f"https://github.com/{github_repo}.git"


def _selected_packages(packages: list[str] | None) -> list[tuple[str, dict]]:
    """Yield (name, info) for selected packages (or all non-archived)."""
    items = []
    for name, info in ECOSYSTEM.items():
        if info.get("archived"):
            continue
        if packages and name not in packages:
            continue
        items.append((name, info))
    return items


def _run(
    cmd: list[str], cwd: Path | None = None, timeout: int = 120
) -> tuple[int, str]:
    """Run a command, return (exit_code, combined output last line)."""
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return r.returncode, (out[-1] if out else "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:  # noqa: BLE001
        return 1, f"{type(e).__name__}: {e}"


def clone_all(
    *,
    dest: Path,
    branch: str = "develop",
    use_ssh: bool = True,
    packages: list[str] | None = None,
    jobs: int = 1,
    dry_run: bool = False,
    on_progress: Callable[[int, int, str, str, str], None] | None = None,
) -> dict[str, tuple[int, str]]:
    """Clone every (selected) ecosystem repo into `dest/<repo-dir>/`.

    Skips packages where the target dir already exists.
    """
    dest = dest.expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    items = _selected_packages(packages)
    results: dict[str, tuple[int, str]] = {}

    def _clone_one(idx: int, total: int, name: str, info: dict) -> None:
        repo_url = (
            _ssh_url(info["github_repo"])
            if use_ssh
            else _https_url(info["github_repo"])
        )
        repo_dir = info["github_repo"].split("/", 1)[1]
        target = dest / repo_dir
        if target.exists():
            results[name] = (0, "exists")
            if on_progress:
                on_progress(idx, total, name, "skip", "exists")
            return
        cmd = ["git", "clone", "--branch", branch, repo_url, str(target)]
        if dry_run:
            results[name] = (0, " ".join(cmd))
            if on_progress:
                on_progress(idx, total, name, "dry", " ".join(cmd))
            return
        rc, msg = _run(cmd)
        results[name] = (rc, msg)
        if on_progress:
            on_progress(idx, total, name, "ok" if rc == 0 else "err", msg)

    if jobs <= 1:
        for i, (name, info) in enumerate(items, 1):
            _clone_one(i, len(items), name, info)
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = [
                ex.submit(_clone_one, i, len(items), name, info)
                for i, (name, info) in enumerate(items, 1)
            ]
            for _ in as_completed(futs):
                pass
    return results


def checkout_all(
    *,
    branch: str = "develop",
    packages: list[str] | None = None,
    on_progress: Callable[[int, int, str, str, str], None] | None = None,
) -> dict[str, tuple[int, str]]:
    """`git checkout <branch>` in every selected repo's local clone."""
    items = _selected_packages(packages)
    results: dict[str, tuple[int, str]] = {}
    for i, (name, info) in enumerate(items, 1):
        local = Path(info["local_path"]).expanduser()
        if not (local / ".git").is_dir():
            results[name] = (1, "not a git repo")
            if on_progress:
                on_progress(i, len(items), name, "err", "not a git repo")
            continue
        rc, msg = _run(["git", "checkout", branch], cwd=local)
        results[name] = (rc, msg)
        if on_progress:
            on_progress(i, len(items), name, "ok" if rc == 0 else "err", msg)
    return results


def pull_all(
    *,
    rebase: bool = True,
    packages: list[str] | None = None,
    jobs: int = 1,
    on_progress: Callable[[int, int, str, str, str], None] | None = None,
) -> dict[str, tuple[int, str]]:
    """`git pull --rebase` in every selected repo (parallel-safe; per-repo)."""
    items = _selected_packages(packages)
    results: dict[str, tuple[int, str]] = {}

    def _pull_one(idx: int, total: int, name: str, info: dict) -> None:
        local = Path(info["local_path"]).expanduser()
        if not (local / ".git").is_dir():
            results[name] = (1, "not a git repo")
            if on_progress:
                on_progress(idx, total, name, "err", "not a git repo")
            return
        cmd = ["git", "pull"] + (["--rebase"] if rebase else [])
        rc, msg = _run(cmd, cwd=local)
        results[name] = (rc, msg)
        if on_progress:
            on_progress(idx, total, name, "ok" if rc == 0 else "err", msg)

    if jobs <= 1:
        for i, (name, info) in enumerate(items, 1):
            _pull_one(i, len(items), name, info)
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = [
                ex.submit(_pull_one, i, len(items), name, info)
                for i, (name, info) in enumerate(items, 1)
            ]
            for _ in as_completed(futs):
                pass
    return results


def install_all(
    *,
    source: str = "editable",
    extras: str = "",
    packages: list[str] | None = None,
    jobs: int = 1,
    dry_run: bool = False,
    venv: str = "per-package",
    upgrade: bool = False,
    no_deps: bool = False,
    on_progress: Callable[[int, int, str, str, str], None] | None = None,
) -> dict[str, tuple[int, str]]:
    """Install every selected package, with **uv** when it is available.

    source: ``editable`` → ``install -e <local_path>[extras]``
            ``pypi``    → ``install <pypi_name>[extras]``

    upgrade: pass ``--upgrade``. OFF by default, deliberately: on a shared
             venv ``-U`` re-resolves DEPENDENCIES too, so a routine refresh
             can move numpy/torch under a package nobody was editing. The
             periodic refresh job turns it on, because currency is the whole
             point there; an interactive install should not surprise anyone.

    no_deps: pass ``--no-deps``. THIS IS THE OTHER HALF OF ``upgrade`` ON A
             SHARED VENV, and it was found the hard way.

             MEASURED 2026-08-17 on /home/ywatanabe/.venv: a `-U` editable
             pass over 22 ecosystem checkouts reported ``ok=22 fail=0`` and
             left scitex-dev, scitex-cards and figrecipe resolving to
             site-packages WHEELS rather than their checkouts. A control
             disproved the obvious culprit — ``uv pip install -U -e <path>``
             on one package keeps the editable, with and without ``-U``. The
             mechanism is ORDER: a LATER package that depends on scitex-dev
             has that dependency re-resolved under ``-U``, and the PyPI wheel
             replaces the editable installed earlier in the same sweep.

             So on a shared venv the correct shape is TWO passes: one that
             may resolve (currency), then one with ``--no-deps`` that cannot
             (re-assert every checkout as editable). A single pass cannot be
             both, and the single-pass result LOOKS successful — the
             installer's own count was 22/22 while three were wrong. Verify a
             shared venv with a functional probe (does each package resolve
             under its checkout?), never with the installer's exit count.

    venv: ``per-package`` (default) → for each package, ensure
                            ``<local>/.venv/`` exists (create with the
                            running Python's ``-m venv`` if absent) and
                            install INTO that venv. Yields the canonical
                            CI-parity layout where every consumer's
                            ``[dev]`` / ``[all]`` extras are exercised
                            in isolation. If ``<local>/.venv`` is a
                            symlink (typically to ``~/.venv`` from a
                            shared-dev setup) it is REPLACED with a real
                            venv so the package's deps don't bleed into
                            the global one.
          ``current``     → install into the currently-running Python
                            (the legacy shared-venv behaviour). Use only
                            when you intentionally want every peer
                            installed into the same env.
    """
    items = _selected_packages(packages)
    results: dict[str, tuple[int, str]] = {}
    extras_suffix = f"[{extras}]" if extras else ""

    def _installer_args(target_py: str, *, upgrade: bool, no_deps: bool) -> list[str]:
        """Build the install argv: uv when present, pip as the fallback.

        BOTH forms are pinned to ``target_py``. uv's ``--python`` and pip's
        ``<py> -m pip`` are the same guarantee — the install lands in the
        interpreter we chose, never in whichever one PATH happens to serve.
        That equivalence is the reason the fallback is safe to keep.

        uv is looked up on PATH and then at ``~/.local/bin/uv``, because a
        systemd unit and a cron line run with a PATH that has neither the
        login shell's additions nor the venv's ``bin/``. Falling back to pip
        rather than failing keeps hosts that predate uv working; the
        operator's ruling (2026-08-17, 「UVを使わないっていうのはありえない
        です」) is about what we USE, and uv is used wherever it exists.
        """
        uv = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
        base = (
            [uv, "pip", "install", "--python", target_py]
            if os.path.isfile(uv) and os.access(uv, os.X_OK)
            else [target_py, "-m", "pip", "install"]
        )
        if upgrade:
            base = base + ["--upgrade"]
        if no_deps:
            base = base + ["--no-deps"]
        return base

    def _ensure_venv(local: Path) -> Path | None:
        """Return path to the venv's python, creating ``<local>/.venv/`` if absent.

        Treats three cases:

        - ``.venv`` missing → create a fresh venv there.
        - ``.venv`` is a symlink (typically points at ``~/.venv`` from a
          shared-dev setup) → break the symlink and create a real venv
          so the package's deps stay isolated from the global one. This
          is the canonical CI-parity guarantee — installing into a
          symlinked .venv silently writes to whatever it points at and
          collides with every other peer.
        - ``.venv`` is a real directory → reuse as-is.
        """
        import os

        venv_dir = local / ".venv"

        if venv_dir.is_symlink():
            # Break the symlink (do NOT follow it — we want to create
            # a real venv at this path, not modify the symlink target).
            try:
                os.unlink(venv_dir)
            except OSError:
                return None

        py = venv_dir / "bin" / "python"
        if not py.exists():
            rc, _msg = _run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                timeout=120,
            )
            if rc != 0:
                return None
            # Upgrade pip in the new venv so subsequent installs use a
            # modern resolver that understands current PEP 517/518 wheels.
            _run(
                [str(py), "-m", "pip", "install", "--upgrade", "pip", "-q"],
                timeout=120,
            )
        return py

    def _install_one(idx: int, total: int, name: str, info: dict) -> None:
        if source == "editable":
            local = Path(info["local_path"]).expanduser()
            if not (local / "pyproject.toml").is_file():
                results[name] = (1, "no pyproject.toml at local_path")
                if on_progress:
                    on_progress(idx, total, name, "err", "missing pyproject")
                return
            target = f"{local}{extras_suffix}"
        elif source == "pypi":
            target = f"{info['pypi_name']}{extras_suffix}"
        else:
            results[name] = (2, f"unknown source: {source}")
            return

        # Pick the python the install must land in.
        if venv == "per-package" and source == "editable":
            local = Path(info["local_path"]).expanduser()
            py = _ensure_venv(local)
            if py is None:
                results[name] = (1, "venv create failed")
                if on_progress:
                    on_progress(idx, total, name, "err", "venv create failed")
                return
            target_py = str(py)
        else:
            # The same Python that's running scitex-dev — never a bare
            # `pip`/`uv`, which resolves the first one on PATH and can be a
            # system Python with stale metadata (e.g. spartan's /usr/bin/pip
            # is 3.9 and cannot see >=3.10 wheels on PyPI).
            target_py = sys.executable

        install_args = _installer_args(target_py, upgrade=upgrade, no_deps=no_deps)
        cmd = (
            install_args + ["-e", target]
            if source == "editable"
            else install_args + [target]
        )
        if dry_run:
            results[name] = (0, " ".join(cmd))
            if on_progress:
                on_progress(idx, total, name, "dry", " ".join(cmd))
            return
        # 21_600 s (6 h) per pkg — `scitex[all,dev]` (the umbrella with
        # full dev extras) is known to take >90 min even with uv, and
        # in some envs runs past 2 h because the dep set pulls torch /
        # jax / playwright browsers / pymupdf / ML-heavy chains.
        # 300 s was the original limit (killed umbrella reliably);
        # 5_400 s (90 min) was an intermediate bump that still tripped.
        # Light peers finish in <60 s either way; the high ceiling
        # matters only for the umbrella + a couple of heavy peers. A
        # genuine pip hang (network or resolver deadlock) at 6 h is
        # the operator's signal to investigate manually.
        rc, msg = _run(cmd, timeout=21_600)
        results[name] = (rc, msg)
        if on_progress:
            on_progress(idx, total, name, "ok" if rc == 0 else "err", msg)

    if jobs <= 1:
        for i, (name, info) in enumerate(items, 1):
            _install_one(i, len(items), name, info)
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = [
                ex.submit(_install_one, i, len(items), name, info)
                for i, (name, info) in enumerate(items, 1)
            ]
            for _ in as_completed(futs):
                pass
    return results


def install_completions_all(
    *,
    shell: str = "bash",
    packages: list[str] | None = None,
    jobs: int = 1,
    dry_run: bool = False,
    on_progress: Callable[[int, int, str, str, str], None] | None = None,
) -> dict[str, tuple[int, str]]:
    """Run `<binary> install-shell-completion --shell <shell> --yes` for every
    selected package.

    Each package's console-script name defaults to its ``pypi_name``
    (e.g. ``scitex-io``). Packages whose binary isn't on PATH are
    reported as a warning, not an error — the package may not yet be
    installed, or may not register a console script.

    Returns: ``{pkg: (exit_code, message)}``.
    """
    import shutil

    items = _selected_packages(packages)
    results: dict[str, tuple[int, str]] = {}

    def _install_one(idx: int, total: int, name: str, info: dict) -> None:
        binary = info.get("pypi_name") or name
        path = shutil.which(binary)
        if path is None:
            results[name] = (0, f"skip: `{binary}` not on PATH")
            if on_progress:
                on_progress(idx, total, name, "skip", f"no binary {binary}")
            return
        cmd = [path, "install-shell-completion", "--shell", shell, "--yes"]
        if dry_run:
            results[name] = (0, " ".join(cmd))
            if on_progress:
                on_progress(idx, total, name, "dry", " ".join(cmd))
            return
        rc, msg = _run(cmd, timeout=60)
        results[name] = (rc, msg)
        if on_progress:
            on_progress(idx, total, name, "ok" if rc == 0 else "err", msg)

    if jobs <= 1:
        for i, (name, info) in enumerate(items, 1):
            _install_one(i, len(items), name, info)
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = [
                ex.submit(_install_one, i, len(items), name, info)
                for i, (name, info) in enumerate(items, 1)
            ]
            for _ in as_completed(futs):
                pass
    return results


__all__ = [
    "clone_all",
    "checkout_all",
    "pull_all",
    "install_all",
    "install_completions_all",
]
