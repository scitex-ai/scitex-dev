#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The cheap pre-gate: correct, and provably cheap.

Two kinds of test live here, and the second is the point.

CORRECTNESS mirrors ``test__cache.py`` deliberately: the fastpath and
``read_cache`` implement ONE trust rule, so they must agree case for case on
missing / corrupt / undated / expired / warm. A divergence here means a
consumer pre-gating on the cheap answer would skip a check the real reader
would have run.

CHEAPNESS is asserted in a SUBPROCESS on ``sys.modules`` membership, not on
wall-clock. A timing threshold on a loaded box is a flaky test that gets
deleted; "did importing the fastpath drag in the heavy machinery?" is a hard
structural fact that stays true under any load. The wall-clock IS recorded
(printed), so a regression is visible to a human reading the output — but it
never fails the build on its own.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from scitex_dev.versioning._config import VersioningConfig
from scitex_dev.versioning._fastpath import (
    DEFAULT_TTL_S,
    cache_is_fresh,
    cached_generated_at,
    cached_state,
    read_cache_raw,
)

CFG = VersioningConfig(dist="scitex-dev")

# The modules a consumer must NOT pay for by pre-gating. `_model` is in the
# list even though it is cheap in itself — see the note in versioning/__init__.
HEAVY = (
    "scitex_dev.versioning._checks",
    "scitex_dev.versioning._sources",
    "scitex_dev.versioning._model",
    "scitex_dev.versioning._cache",
    "scitex_dev.versioning._config",
    "scitex_dev.versioning._warn",
)

FASTPATH_SRC = Path(
    __import__("scitex_dev.versioning._fastpath", fromlist=["_fastpath"]).__file__
)


def _payload(state="stale", at=None):
    return {
        "state": state,
        "generated_at": time.time() if at is None else at,
        "findings": [
            {
                "check": "install-currency",
                "state": state,
                "summary": "installed 0.29.0 is BEHIND PyPI 0.31.0",
                "remedy": "python -m pip install -U 'scitex-dev==0.31.0'",
            }
        ],
    }


def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# -- correctness: not-fresh is the answer whenever we are unsure -----------


def test_warm_cache_is_fresh(tmp_path):
    # Arrange
    path = _write(tmp_path / "c.json", _payload(at=time.time() - 60))
    # Act
    fresh = cache_is_fresh(path)
    # Assert
    assert fresh is True


def test_missing_cache_is_not_fresh(tmp_path):
    # Arrange
    path = tmp_path / "nope.json"
    # Act
    fresh = cache_is_fresh(path)
    # Assert
    assert fresh is False


def test_corrupt_cache_is_not_fresh(tmp_path):
    # Arrange
    path = tmp_path / "c.json"
    path.write_text("{ this is not json")
    # Act
    fresh = cache_is_fresh(path)
    # Assert
    assert fresh is False


def test_non_object_cache_is_not_fresh(tmp_path):
    # Arrange
    path = _write(tmp_path / "c.json", ["a", "list"])
    # Act
    fresh = cache_is_fresh(path)
    # Assert
    assert fresh is False


def test_undated_cache_is_not_fresh(tmp_path):
    # Arrange
    path = _write(tmp_path / "c.json", {"state": "stale", "findings": []})
    # Act
    fresh = cache_is_fresh(path)
    # Assert
    assert fresh is False


def test_expired_cache_is_not_fresh(tmp_path):
    # Arrange
    path = _write(tmp_path / "c.json", _payload(at=time.time() - DEFAULT_TTL_S - 60))
    # Act
    fresh = cache_is_fresh(path)
    # Assert
    assert fresh is False


def test_unreadable_directory_is_not_fresh(tmp_path):
    # Arrange — a directory where a file is expected: OSError, not a crash.
    path = tmp_path / "c.json"
    path.mkdir()
    # Act
    fresh = cache_is_fresh(path)
    # Assert
    assert fresh is False


def test_garbage_argument_is_not_fresh():
    # Arrange — not a config, not a path. Must not raise.
    # Act
    fresh = cache_is_fresh(object())
    # Assert
    assert fresh is False


def test_config_resolves_the_same_cache_the_writer_uses(tmp_path, env):
    # Arrange
    target = tmp_path / "elsewhere.json"
    env(CFG.env_cache, str(target))
    _write(target, _payload(at=time.time() - 60))
    # Act
    fresh = cache_is_fresh(CFG)
    # Assert
    assert fresh is True


def test_ttl_env_override_expires_the_cache(tmp_path, env):
    # Arrange
    target = tmp_path / "c.json"
    env(CFG.env_cache, str(target))
    env(CFG.env_ttl, "10")
    _write(target, _payload(at=time.time() - 60))
    # Act
    fresh = cache_is_fresh(CFG)
    # Assert
    assert fresh is False


def test_injected_now_drives_expiry(tmp_path):
    # Arrange
    generated = 1_000_000.0
    path = _write(tmp_path / "c.json", _payload(at=generated))
    # Act
    fresh = cache_is_fresh(path, now=generated + DEFAULT_TTL_S + 1)
    # Assert
    assert fresh is False


def test_cached_state_reports_the_verdict(tmp_path):
    # Arrange
    path = _write(tmp_path / "c.json", _payload(state="stale", at=time.time() - 60))
    # Act
    state = cached_state(path)
    # Assert
    assert state == "stale"


def test_cached_state_is_none_when_not_warm(tmp_path):
    # Arrange
    path = _write(tmp_path / "c.json", _payload(at=time.time() - DEFAULT_TTL_S - 60))
    # Act
    state = cached_state(path)
    # Assert
    assert state is None


def test_cached_generated_at_reports_the_stamp(tmp_path):
    # Arrange
    generated = time.time() - 60
    path = _write(tmp_path / "c.json", _payload(at=generated))
    # Act
    stamp = cached_generated_at(path)
    # Assert
    assert stamp == pytest.approx(generated)


def test_read_cache_raw_returns_the_payload(tmp_path):
    # Arrange
    path = _write(tmp_path / "c.json", _payload(at=time.time() - 60))
    # Act
    raw = read_cache_raw(path)
    # Assert
    assert raw["findings"][0]["check"] == "install-currency"


# -- one rule, two readers: the fastpath and read_cache must agree ---------


@pytest.mark.parametrize(
    "name,payload",
    [
        ("warm", _payload(at=time.time() - 60)),
        ("expired", _payload(at=time.time() - DEFAULT_TTL_S - 60)),
        ("undated", {"state": "stale", "findings": []}),
        ("non-object", ["a", "list"]),
    ],
)
def test_fastpath_agrees_with_read_cache(tmp_path, name, payload):
    # Arrange
    from scitex_dev.versioning._cache import read_cache

    path = _write(tmp_path / "c.json", payload)
    # Act
    cheap = cache_is_fresh(path)
    full = read_cache(CFG, path) is not None
    # Assert
    assert cheap == full, f"cheap and full readers disagree on the {name} cache"


def test_fastpath_agrees_with_read_cache_on_missing(tmp_path):
    # Arrange
    from scitex_dev.versioning._cache import read_cache

    path = tmp_path / "nope.json"
    # Act
    cheap = cache_is_fresh(path)
    full = read_cache(CFG, path) is not None
    # Assert
    assert cheap == full


# -- cheapness: asserted structurally, in a clean interpreter --------------


def _run(script: str) -> dict:
    """Run a script in a CLEAN subprocess and return its JSON verdict.

    A subprocess is not optional here: this test module has already imported
    the whole package, so `sys.modules` in-process proves nothing at all.
    """
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def standalone(tmp_path_factory):
    """Load the fastpath by FILE LOCATION in a clean interpreter, once.

    This is the real hot path — the ~0.02 ms mode a CLI actually wires, and
    the one that proves the module has no relative imports and no package
    dependency at all. Module-scoped so the several one-assert tests below
    interrogate a single measured run rather than paying for four.
    """
    cache = _write(
        tmp_path_factory.mktemp("standalone") / "c.json",
        _payload(at=time.time() - 60),
    )
    verdict = _run(
        f"""
        import importlib.util, json, sys, time
        t = time.perf_counter()
        spec = importlib.util.spec_from_file_location("_fp", {str(FASTPATH_SRC)!r})
        fp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fp)
        fresh = fp.cache_is_fresh({str(cache)!r})
        elapsed_ms = (time.perf_counter() - t) * 1000
        print(json.dumps({{
            "fresh": fresh,
            "elapsed_ms": elapsed_ms,
            "scitex_dev_loaded": "scitex_dev" in sys.modules,
            "leaked": sorted(m for m in sys.modules if m.startswith("scitex_dev")),
        }}))
        """
    )
    print(f"\n[fastpath] standalone load + read: {verdict['elapsed_ms']:.3f} ms")
    return verdict


def test_standalone_load_reads_the_warm_cache(standalone):
    # Arrange
    verdict = standalone
    # Act
    fresh = verdict["fresh"]
    # Assert
    assert fresh is True


def test_standalone_load_never_imports_scitex_dev(standalone):
    # Arrange
    verdict = standalone
    # Act
    leaked = verdict["leaked"]
    # Assert
    assert leaked == [], f"standalone load dragged in {leaked}"


def test_standalone_load_costs_less_than_the_package_it_replaces(standalone):
    """A tripwire with a MEANING, not a stopwatch with a guessed number.

    The threshold is 100 ms because that is the scale of the thing this
    module exists to avoid: importing the package costs ~150-250 ms. Crossing
    100 ms therefore means the cheap path stopped being meaningfully cheaper
    than the expensive one — the only timing regression worth failing a build
    over.

    It is deliberately NOT tuned to the observed number. Measured in a plain
    interpreter the load is ~0.6-5 ms, but this suite runs under coverage
    tracing on a loaded WSL2 box, where the same work reports 25-40 ms. A
    threshold set near that would fail on machine load rather than on a code
    change, and a test that fails for reasons unrelated to the code gets
    deleted — taking the real signal with it.

    The structural `sys.modules` assertions above are the actual guarantee.
    This only catches a stdlib import (urllib, say) heavy enough to matter
    yet invisible to them.
    """
    # Arrange
    verdict = standalone
    # Act
    elapsed = verdict["elapsed_ms"]
    # Assert
    assert elapsed < 100, f"fastpath standalone load regressed to {elapsed:.1f} ms"


@pytest.fixture(scope="module")
def pathlib_free(tmp_path_factory):
    """Pre-gate on a STRING path in an interpreter with `pathlib` unloaded.

    A cold `from pathlib import Path` is ~10-15 ms — a tenth of sac's whole
    CLI budget spent on a convenience type. `pathlib` is usually already
    loaded (a venv `.pth` often pulls it in during `site` processing), which
    is exactly why this needs a test: the property would otherwise be
    satisfied by accident and silently lost. `-S` skips `site` so the
    interpreter genuinely starts without it.
    """
    cache = _write(
        tmp_path_factory.mktemp("pathlibfree") / "c.json",
        _payload(at=time.time() - 60),
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            textwrap.dedent(
                f"""
                import importlib.util, json, sys
                before = "pathlib" in sys.modules
                spec = importlib.util.spec_from_file_location(
                    "_fp", {str(FASTPATH_SRC)!r}
                )
                fp = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(fp)
                fresh = fp.cache_is_fresh({str(cache)!r})
                print(json.dumps({{
                    "pathlib_before": before,
                    "pathlib_after": "pathlib" in sys.modules,
                    "fresh": fresh,
                }}))
                """
            ),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, f"subprocess failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_hot_path_starts_without_pathlib_loaded(pathlib_free):
    """Guards the test itself: if `-S` stopped working, the next test lies."""
    # Arrange
    verdict = pathlib_free
    # Act
    before = verdict["pathlib_before"]
    # Assert
    assert before is False


def test_string_path_pre_gate_never_imports_pathlib(pathlib_free):
    # Arrange
    verdict = pathlib_free
    # Act
    after = verdict["pathlib_after"]
    # Assert
    assert after is False, "the read path pulled in pathlib"


def test_string_path_pre_gate_still_reads_the_warm_cache(pathlib_free):
    # Arrange
    verdict = pathlib_free
    # Act
    fresh = verdict["fresh"]
    # Assert
    assert fresh is True


@pytest.fixture(scope="module")
def submodule_import():
    """Import `scitex_dev.versioning._fastpath` the ordinary way, cleanly.

    This one still pays for the parent `scitex_dev` package (Python imports
    parents first — that is the ~200 ms the standalone load exists to dodge),
    but it must not pull `_checks` / `_sources` / `_model` on top.
    """
    src = str(FASTPATH_SRC.parents[2])
    return _run(
        f"""
        import json, sys
        sys.path.insert(0, {src!r})
        import scitex_dev.versioning._fastpath as fp
        print(json.dumps({{
            "loaded": sorted(m for m in sys.modules if m in {list(HEAVY)!r}),
            "has_gate": callable(fp.cache_is_fresh),
        }}))
        """
    )


def test_fastpath_submodule_exposes_the_gate(submodule_import):
    # Arrange
    verdict = submodule_import
    # Act
    has_gate = verdict["has_gate"]
    # Assert
    assert has_gate is True


def test_fastpath_submodule_leaves_heavy_modules_unloaded(submodule_import):
    # Arrange
    verdict = submodule_import
    # Act
    loaded = verdict["loaded"]
    # Assert
    assert loaded == [], f"fastpath dragged in {loaded}"


@pytest.fixture(scope="module")
def public_export(tmp_path_factory):
    """`from scitex_dev.versioning import cache_is_fresh`, in a clean process.

    Requirement 4: wiring the gate into the public surface must not be the
    thing that un-does it. If someone re-adds an eager `from ._model import
    ...` to `versioning/__init__.py`, the companion test fails.
    """
    src = str(FASTPATH_SRC.parents[2])
    cache = _write(
        tmp_path_factory.mktemp("public") / "c.json",
        _payload(at=time.time() - 60),
    )
    return _run(
        f"""
        import json, sys
        sys.path.insert(0, {src!r})
        from scitex_dev.versioning import cache_is_fresh
        fresh = cache_is_fresh({str(cache)!r})
        print(json.dumps({{
            "fresh": fresh,
            "loaded": sorted(m for m in sys.modules if m in {list(HEAVY)!r}),
        }}))
        """
    )


def test_public_lazy_export_reads_the_warm_cache(public_export):
    # Arrange
    verdict = public_export
    # Act
    fresh = verdict["fresh"]
    # Assert
    assert fresh is True


def test_public_lazy_export_does_not_load_the_heavy_modules(public_export):
    # Arrange
    verdict = public_export
    # Act
    loaded = verdict["loaded"]
    # Assert
    assert loaded == [], f"public export dragged in {loaded}"


# -- the heavy API must still work, unchanged -----------------------------


def test_heavy_public_api_still_imports():
    """Every documented name must survive the move to a fully-lazy __init__."""
    # Arrange
    import scitex_dev.versioning as versioning

    names = [
        "Currency",
        "Finding",
        "Report",
        "LiveSources",
        "StaticSources",
        "VersioningConfig",
        "cache_path",
        "check_currency",
        "read_cache",
        "warn_if_stale",
        "write_cache",
    ]
    # Act
    missing = [n for n in names if not hasattr(versioning, n)]
    # Assert
    assert missing == []


def test_check_currency_still_runs_against_static_sources():
    # Arrange
    from scitex_dev.versioning import Currency, StaticSources, check_currency

    sources = StaticSources()
    # Act
    report = check_currency(CFG, sources)
    # Assert — no evidence at all is UNKNOWN, never FRESH.
    assert report.state is Currency.UNKNOWN


def test_cache_round_trip_still_works_through_the_refactored_reader(tmp_path):
    # Arrange
    from scitex_dev.versioning import Currency, read_cache, write_cache
    from scitex_dev.versioning._model import Finding, Report

    path = tmp_path / "c.json"
    report = Report(
        findings=(
            Finding(
                check="install-currency",
                state=Currency.STALE,
                summary="installed 0.29.0 is BEHIND PyPI 0.31.0",
                remedy="python -m pip install -U 'scitex-dev==0.31.0'",
            ),
        ),
        generated_at=time.time(),
    )
    write_cache(CFG, report, path)
    # Act
    loaded = read_cache(CFG, path)
    # Assert
    assert loaded.state is Currency.STALE


# EOF
