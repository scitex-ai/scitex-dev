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
    # ORDER MATTERS, AND SO DOES THE GUARD. The previous shim read
    # `import os, coverage` on its FIRST line, so every Python process in the
    # environment imported coverage at interpreter startup — and where
    # coverage was absent, `site` printed a ModuleNotFoundError traceback to
    # stderr and carried on. Measured across the fleet 2026-08-12: four
    # tracebacks before any real output, on every interpreter start, because
    # scitex-container ships an identical file.
    #
    # The cost is not the noise. It is that a channel RESERVED FOR PROBLEMS
    # was filled with a permanent non-problem, so everyone learned to skim
    # stderr — which is where the next real error appears. Fail-loud inverted
    # by accident.
    #
    # Checking the env var FIRST also means a non-test process imports
    # nothing at all, rather than paying for a coverage import it will never
    # use. A `.pth` runs before anything can catch it, so it must be the
    # cheapest and quietest thing in the process.
    shim = (
        "import os\n"
        "if os.environ.get('COVERAGE_PROCESS_START'):\n"
        "    try:\n"
        "        import coverage\n"
        "    except ImportError:\n"
        "        pass\n"
        "    else:\n"
        "        coverage.process_startup()\n"
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

# >>> scitex-dev audit-gate collection guard >>>
# Generated by `scitex-dev ecosystem install-audit-gate`. Regenerate with
# that command; edits inside this block are overwritten.
#
# WHY: the audit gate lives at tests/develop/test_audit.py, outside the
# tests/<pkg>/ directory you naturally run while working. Without this,
# `pytest tests/<pkg>/` reports a clean green having never run the gate,
# and CI is the first thing that does.
#
# WHAT: a session that would otherwise report SUCCESS, but never
# collected OR ran the gate, fails instead — naming the reason. An
# already-red session is left alone. Opt out for one run with
# SCITEX_DEV_ALLOW_PARTIAL_RUN=1.
import os as _stx_os
from pathlib import Path as _stx_Path

_STX_GATE_RELPARTS = ('tests', 'develop', 'test_audit.py')
_STX_GATE_NODEID_PREFIX = 'tests/develop/test_audit.py'
_STX_OPT_OUT = 'SCITEX_DEV_ALLOW_PARTIAL_RUN'
_stx_gate_seen = False


def _stx_gate_path(config):
    """Absolute path of the audit gate for this rootdir."""
    root = getattr(config, "rootpath", None) or getattr(config, "rootdir", "")
    return _stx_Path(str(root)).joinpath(*_STX_GATE_RELPARTS)


# ---------------------------------------------------------------------------
# A DECLARED ini SETTING THAT NOTHING IMPLEMENTS MUST NOT BE SILENT.
#
# `[tool.pytest.ini_options]` accepts any key. If no installed plugin
# registers it, pytest emits `PytestConfigWarning: Unknown config option`
# and CARRIES ON — the setting is inert, and the run looks identical to
# one where it applied.
#
# `timeout = 300` is the key with a stake attached. pytest-timeout lives
# in the `[dev]` extra, so a venv installed without it runs this suite
# with NO per-test cap and says so only in a warning nobody reads.
# Measured 2026-07-29 by scitex-hpc on a live host running this suite:
#
#     pytest_timeout spec: ABSENT
#     registered third-party plugins:   (empty)
#
# So the guard whose comment promises "a single hung test fails loud +
# names itself in ~5 min instead of wedging the whole job until GitHub's
# 6h ceiling" was, on that host, doing nothing at all. It had been
# visibly present and invisibly optional since 2026-06-16 (#206) — six
# weeks for such environments to accumulate, and six weeks of readers
# (me included) reasonably concluding that hangs were bounded.
#
# The check is deliberately GENERAL rather than a `timeout` special-case:
# `timeout` is merely the key we noticed. Any declared-but-unimplemented
# setting is the same defect with a different stake.
#
# Promoting `PytestConfigWarning` to an error via `-W` also catches this,
# but it surfaces as an INTERNALERROR traceback that names no remedy.
# This says which key, which plugin, and what to do.
_STX_INI_PROVIDERS = {
    "timeout": "pytest-timeout",
    "timeout_method": "pytest-timeout",
}


def _stx_declared_ini_keys(config):
    """ini keys this repo's pyproject declares, or () if unreadable."""
    root = getattr(config, "rootpath", None) or getattr(config, "rootdir", "")
    pyproject = _stx_Path(str(root)) / "pyproject.toml"
    try:
        import tomllib

        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, ImportError, ValueError):
        # Running against an installed package, or an unreadable/invalid
        # pyproject: nothing is declared here, so nothing can be inert.
        return ()
    return tuple(data.get("tool", {}).get("pytest", {}).get("ini_options", {}))


def pytest_configure(config):
    """Fail if a declared ini setting is not implemented by anything."""
    inert = []
    for key in _stx_declared_ini_keys(config):
        try:
            config.getini(key)
        except ValueError:
            inert.append(key)
    if not inert:
        return
    lines = [
        "INERT PYTEST CONFIG — declared settings that nothing implements:",
        "",
    ]
    for key in inert:
        provider = _STX_INI_PROVIDERS.get(key)
        hint = f"install `{provider}`" if provider else "no known provider"
        lines.append(f"  {key}  -> not registered by any plugin ({hint})")
    lines += [
        "",
        "pyproject declares these, pytest accepted them, and NOTHING APPLIES",
        "them. This run behaves as if they were absent while reporting the",
        "same result as a run where they applied.",
        "",
        "If `timeout` is listed, THIS RUN HAS NO PER-TEST CAP: a hung test",
        "wedges the job to the CI ceiling instead of failing in ~5 min.",
        "",
        "Fix:  pip install -e '.[dev]'   (installs the plugins the config"
        " assumes)",
    ]
    raise pytest.UsageError("\n".join(lines))


def pytest_collection_modifyitems(session, config, items):
    """Record the gate being COLLECTED (fires in-process / in xdist workers).

    The only signal that fires for a session which collects the gate
    without running it (``--collect-only``, or an early exit).
    """
    global _stx_gate_seen
    try:
        gate = _stx_gate_path(config).resolve()
    except OSError:  # pragma: no cover - defensive
        return
    for item in items:
        try:
            if _stx_Path(str(item.fspath)).resolve() == gate:
                _stx_gate_seen = True
                return
        except OSError:  # pragma: no cover - defensive
            continue


def pytest_runtest_logreport(report):
    """Record the gate RUNNING — the signal that reaches an xdist controller.

    Under ``-n auto`` the controller never collects, so the collection
    hook above never fires there; xdist DOES forward every worker's test
    reports to it. Without this, a fully green ``-n auto`` run that
    collected and passed the gate is still reported as gate-less.
    ``nodeid`` is always rootdir-relative with ``/`` separators.
    """
    global _stx_gate_seen
    if _stx_gate_seen:
        return
    nodeid = getattr(report, "nodeid", "") or ""
    if nodeid.split("::", 1)[0] == _STX_GATE_NODEID_PREFIX:
        _stx_gate_seen = True


def pytest_sessionfinish(session, exitstatus):
    """Turn an unqualified green from a gate-less run into a loud red."""
    if _stx_gate_seen or exitstatus != 0:
        return
    config = session.config
    if hasattr(config, "workerinput"):
        return  # xdist worker; the controller reports for the session
    if _stx_os.environ.get(_STX_OPT_OUT):
        return
    gate = _stx_gate_path(config)
    if not gate.is_file():
        return  # this repo has no audit gate installed - nothing to miss
    message = (
        "AUDIT GATE DID NOT RUN IN THIS SESSION.\n"
        f"  {gate} was never collected, so this green says nothing "
        "about audit conformance -\n"
        "  it is the same green you would get with the gate failing.\n"
        "  Run the whole tree:  pytest tests/\n"
        f"  Or accept a partial run for THIS run:  {_STX_OPT_OUT}=1 pytest ..."
    )
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_sep("=", "audit gate not collected", red=True, bold=True)
        for line in message.splitlines():
            reporter.write_line(line, red=True)
    else:  # pragma: no cover - terminal plugin disabled
        print(message)
    session.exitstatus = 1
# <<< scitex-dev audit-gate collection guard <<<
