"""Pytest fixtures and rootdir marker for this package.

An empty conftest.py at tests/ is the canonical SciTeX
convention (audit-project PS-208) — it pins the pytest
rootdir and gives downstream fixtures a home.

Also wires subprocess coverage at module import time so child Python
interpreters (subprocess.run([sys.executable, ...]), demo smoke tests,
etc.) write their coverage data into the same shard pool as the parent.
See ``src/scitex_dev/_skills/general/05_development/06_subprocess-coverage.md``.

Critical: we force-set (not setdefault) ``COVERAGE_PROCESS_START`` and
``COVERAGE_FILE`` because pytest-cov has already set ``COVERAGE_FILE`` to
a per-test tmp dir by the time conftest loads — ``setdefault`` would be a
silent no-op and the fix would appear to "do nothing".
"""

from __future__ import annotations

import os
import sysconfig
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping, MutableMapping

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Pin coverage's data file at the repo root and point process_startup at
# our pyproject so child interpreters configure themselves correctly.
os.environ["COVERAGE_PROCESS_START"] = str(_PROJECT_ROOT / "pyproject.toml")
os.environ["COVERAGE_FILE"] = str(_PROJECT_ROOT / ".coverage")


def _ensure_subprocess_coverage_shim() -> None:
    """Drop an idempotent ``.pth`` file in site-packages that auto-starts
    coverage in every child Python interpreter via
    ``coverage.process_startup()``.
    """
    purelib = Path(sysconfig.get_paths()["purelib"])
    pth = purelib / "_scitex_dev_subprocess_coverage.pth"
    shim = (
        "import os, coverage\n"
        "if os.environ.get('COVERAGE_PROCESS_START'):\n"
        "    coverage.process_startup()\n"
    )
    try:
        if not pth.exists() or pth.read_text() != shim:
            pth.write_text(shim)
    except OSError:
        # site-packages may be read-only (e.g. system Python); silently
        # skip — local dev venvs are writable and that's where it matters.
        pass


_ensure_subprocess_coverage_shim()


# --------------------------------------------------------------------------- #
# Live card-store shield (incident 2026-07-21 — third store wipe)             #
# --------------------------------------------------------------------------- #
#
# The fleet's canonical scitex-cards store (~/.scitex/cards/cards.db) was
# mass-DELETEd by full-suite pytest runs executing with the session's AMBIENT
# environment, where SCITEX_CARDS_DB / SCITEX_TODO_* pointed at the live
# store — tests exercising store-writing code paths then hit production data.
# The fixture below is this repo's mechanical barrier: BEFORE any test runs,
# every environment variable that can steer store resolution is FORCE-SET
# (never setdefault — see the coverage note above for why setdefault silently
# no-ops here) to a throwaway per-session tmp path.
#
# REPOINT, never merely unset: with these vars absent, scitex-cards (and
# scitex-dev's own _task_harvest) fall back to the default $HOME-based paths
# (~/.scitex/cards/cards.db, ~/.scitex/todo/tasks.yaml) — i.e. unsetting
# routes straight back to the live store. Explicit tmp paths cover both the
# env tier and the HOME-fallback tier of every resolution chain.
#
# Both SCITEX_CARDS_* and SCITEX_TODO_* twins are set for every suffix:
# scitex_cards._env_compat.mirror_env() copies CARDS_* onto TODO_* at import
# time with "new name wins", so a shielded TODO_* var would otherwise be
# clobbered by an ambient live CARDS_* twin.

#: path-bearing store vars: suffix -> tmp filename it is repointed to.
_STORE_PATH_SUFFIXES: dict[str, str] = {
    "DB": "cards.db",
    "TASKS": "tasks.yaml",
    "TASKS_YAML": "tasks.yaml",
    "TASKS_YAML_SHARED": "tasks.yaml",
    "INBOX_DB": "inbox.db",
    "INDEX_PATH": "index.json",
    "CI_STATE": "ci-state.json",
    "BOARD_PIDFILE": "board.pid",
}

#: behaviour selectors forced to the local-file backend / disabled rails.
_STORE_VALUE_SUFFIXES: dict[str, str] = {
    "STORE_BACKEND": "sqlite",
    "INBOX_BACKEND": "sqlite",
    "DUAL_WRITE": "0",
    "STORE_GIT_AUTOCOMMIT": "0",
}

#: remote-hub endpoints — there is no tmp equivalent of a live URL, and with
#: these absent scitex_cards._backend resolves to the LOCAL (tmp) backend.
_STORE_UNSET_SUFFIXES: tuple[str, ...] = (
    "HUB_URL",
    "HUB_TOKEN",
    "HUB_TOKEN_FILE",
)

_ENV_PREFIXES = ("SCITEX_CARDS_", "SCITEX_TODO_")

_STORE_PATH_ENV: dict[str, str] = {
    prefix + suffix: filename
    for prefix in _ENV_PREFIXES
    for suffix, filename in _STORE_PATH_SUFFIXES.items()
}
_STORE_VALUE_ENV: dict[str, str] = {
    prefix + suffix: value
    for prefix in _ENV_PREFIXES
    for suffix, value in _STORE_VALUE_SUFFIXES.items()
}
_STORE_UNSET_ENV: tuple[str, ...] = tuple(
    prefix + suffix for prefix in _ENV_PREFIXES for suffix in _STORE_UNSET_SUFFIXES
)

#: every var the shield touches (SCITEX_DIR relocates the whole ~/.scitex
#: user root, covering resolvers that build store paths from it).
_SHIELDED_ENV_VARS: tuple[str, ...] = (
    "SCITEX_DIR",
    *_STORE_PATH_ENV,
    *_STORE_VALUE_ENV,
    *_STORE_UNSET_ENV,
)


def _live_store_paths(
    environ: Mapping[str, str], home: Path
) -> frozenset[Path]:
    """Every path that could be the fleet's LIVE store, resolved.

    Built from the PRE-shield environment: the default ``$HOME``-based store
    locations (plus their ``$SCITEX_DIR`` equivalents) and whatever the
    ambient path-bearing store vars pointed at.
    """
    roots = {home / ".scitex"}
    scitex_dir = environ.get("SCITEX_DIR")
    if scitex_dir:
        roots.add(Path(scitex_dir).expanduser())
    candidates: set[Path] = set()
    for root in roots:
        candidates.add(root / "cards" / "cards.db")
        candidates.add(root / "todo" / "cards.db")
        candidates.add(root / "todo" / "tasks.yaml")
        candidates.add(root / "todo" / "inbox.db")
    for var in _STORE_PATH_ENV:
        value = environ.get(var)
        if value:
            candidates.add(Path(value).expanduser())
    return frozenset(path.resolve() for path in candidates)


def _apply_shield(environ: MutableMapping[str, str], tmp_dir: Path) -> None:
    """FORCE-SET every store var to a path/value inside ``tmp_dir``."""
    user_root = tmp_dir / "scitex-user-root"
    user_root.mkdir(parents=True, exist_ok=True)
    environ["SCITEX_DIR"] = str(user_root)
    for var, filename in _STORE_PATH_ENV.items():
        environ[var] = str(tmp_dir / filename)
    tasks_yaml = tmp_dir / "tasks.yaml"
    if not tasks_yaml.exists():
        # empty-but-valid store: readers require a top-level ``tasks`` key.
        tasks_yaml.write_text("tasks: []\n", encoding="utf-8")
    for var, value in _STORE_VALUE_ENV.items():
        environ[var] = value
    for var in _STORE_UNSET_ENV:
        environ.pop(var, None)


def _resolved_store_target(environ: Mapping[str, str]) -> Path:
    """The store path a writer would actually hit, per scitex_cards.

    Uses the real scitex_cards resolution chain when the package is
    importable (the exact code the wipe went through); otherwise falls back
    to the env values themselves.
    """
    try:
        from scitex_cards._db import resolve_db_path

        return Path(resolve_db_path()).expanduser()
    except Exception:
        value = environ.get("SCITEX_CARDS_DB") or environ.get("SCITEX_TODO_DB")
        if value:
            return Path(value).expanduser()
        return Path.home() / ".scitex" / "cards" / "cards.db"


def _assert_shielded(resolved: Path, live_paths: frozenset[Path]) -> None:
    """Fail LOUD when ``resolved`` is one of the LIVE store paths."""
    resolved = Path(resolved).expanduser().resolve()
    if resolved in live_paths:
        raise RuntimeError(
            "live-store shield FAILED: the resolved card store "
            f"{resolved} is a LIVE fleet store path. Refusing to run any "
            "test against production card data (incident 2026-07-21, "
            "third store wipe). Check tests/conftest.py "
            "_shield_live_card_store."
        )


@pytest.fixture(scope="session", autouse=True)
def _shield_live_card_store(
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Session barrier: no test may ever see the LIVE scitex-cards store.

    Captures the live paths from the pre-shield environment, repoints every
    store var into a per-session tmp directory, then asserts the resolved
    store target is NOT live. Never restores mid-session; the original env
    is restored only at session teardown (pytest-embedding safety).
    """
    saved_env = {var: os.environ.get(var) for var in _SHIELDED_ENV_VARS}
    live_paths = _live_store_paths(os.environ, Path.home())
    tmp_dir = Path(tmp_path_factory.mktemp("live-store-shield"))
    _apply_shield(os.environ, tmp_dir)
    _assert_shielded(_resolved_store_target(os.environ), live_paths)
    yield SimpleNamespace(
        tmp_dir=tmp_dir, live_paths=live_paths, saved_env=saved_env
    )
    for var, value in saved_env.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value
