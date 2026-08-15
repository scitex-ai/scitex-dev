#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CURRENCY gate — version-currency + install-integrity primitive.

Public, reusable entry point for any SciTeX package that wants to refuse to
run (or warn) when its own install is stale or broken (operator directive
2026-07-21: a latest-version check must fire on invocation, at ERROR
severity by default — 「普通は warning ですが、私たちはエラーを選びます」,
normally this would be a warning, but we choose error).

Consumers wire it fail-open at their entry points::

    try:
        from scitex_dev.staleness import ensure_current
        ensure_current("scitex-cards")
    except ImportError:
        pass

Two halves:

1. INTEGRITY (always runs, purely local, no network):
   - multiple ``*.dist-info`` directories claiming the same distribution in
     one site dir → "ambiguous metadata";
   - any file listed in the resolved distribution's RECORD missing on disk →
     "partial install".
   Motivating incident (2026-07-21): a venv carried 0.16.0 + 0.17.4
   dist-infos, with 0.17.4 metadata over a 0.16-era file set;
   ``_store_backend.py`` was in RECORD but absent on disk, so every version
   probe lied. This half catches exactly that. Editable installs (PEP 610
   ``direct_url.json`` editable flag) are skipped here — RECORD is
   meaningless for them; the freshness half governs them instead.

2. FRESHNESS (fail-safe — no evidence / offline / any error → PASS):
   - wheel install: installed version vs a cached latest (PyPI is truth;
     read from a pre-existing per-dist cache file, opportunistically
     refreshed in a detached background process — NEVER a blocking live
     PyPI call on the invocation path);
   - editable install: HEAD behind its tracking remote (reuses the
     editable-drift git machinery).

Severity: explicit arg > ``$SCITEX_DEV_CURRENCY_SEVERITY`` >
``currency_severity`` knob (config.yaml → knob-state.json) > default
``error``. ``error`` raises :class:`StalenessError` (message carries the
exact remedy command); ``warn`` emits via scitex-logging and returns;
``silent`` is a no-op.

``SCITEX_DEV_NO_CURRENCY_GATE=1`` bypasses BOTH halves but logs a loud WARN
— an exercised bypass must be visible, never silent.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
import time
from importlib.metadata import Distribution
from pathlib import Path

from scitex_dev._release.check_editable_drift import (
    _cached_latest,
    _compute_drift,
    _editable_dir_from_meta,
    _is_older,
    _log_stale,
    _resolve_severity,
)
from scitex_dev._release.dist_info_integrity import AMBIGUOUS_METADATA_REMEDY

_ENV_BYPASS = "SCITEX_DEV_NO_CURRENCY_GATE"
_ENV_SEVERITY = "SCITEX_DEV_CURRENCY_SEVERITY"
_ENV_CACHE_DIR = "SCITEX_DEV_VERSION_CACHE_DIR"
_ENV_NO_REFRESH = "SCITEX_DEV_NO_CURRENCY_REFRESH"
_SEVERITIES = ("silent", "warn", "error")
_DEFAULT_SEVERITY = "error"
# Cache entries older than this trigger an opportunistic background refresh.
# A present-but-old entry is still COMPARED (versions only move forward, so
# "behind an old latest" implies "behind the current latest").
_CACHE_TTL_SECONDS = 24 * 3600
# Throttle for background refresh attempts (marker-file mtime).
_REFRESH_MIN_INTERVAL_SECONDS = 600
_SUPPRESS_HINT = (
    "suppress: SCITEX_DEV_NO_CURRENCY_GATE=1 · severity: currency_severity knob"
)



class StalenessError(RuntimeError):
    """A distribution is stale or its on-disk install is broken.

    Raised by :func:`ensure_current` at ``error`` severity. The message
    always carries the exact remedy command (``pip install -U <dist>`` /
    ``git -C <path> pull --ff-only`` / a forced reinstall for integrity
    violations).
    """


def _canonical(name: str) -> str:
    """PEP 503 canonical form: runs of ``-_.`` → ``-``, lowercased."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _is_installed_dist_info(path: Path) -> bool:
    """True when ``path`` is a REAL installed distribution's dist-info.

    A NAME MATCH IS NOT EVIDENCE OF AN INSTALL. Two INDEPENDENT conditions
    must both hold, because on an overlay filesystem (every containerised
    agent) at least three different things can occupy a ``*.dist-info``
    name and a bare name-match renders them identically:

    1. IT MUST ACTUALLY BE A DIRECTORY. An overlayfs WHITEOUT — the marker
       written when an upper layer deletes an entry that exists in a lower
       layer — is a character-special device node (major 0, minor 0), not a
       directory. ``Path.is_dir()`` stats the entry and tests ``S_ISDIR``,
       so it is False for a whiteout; the TYPE test, not the name, is what
       rejects it.
    2. IT MUST CONTAIN A ``METADATA`` ENTRY. A dist-info directory with no
       METADATA is not an installed distribution — it is filesystem
       residue. ``pip uninstall`` removes a dist-info's FILES; on an
       overlay the now-empty DIRECTORY can survive as an entry showing
       through from the lower layer.

    DELIBERATE DECISION — a PRESENT-BUT-UNREADABLE ``METADATA`` COUNTS.
    The discriminator is EXISTENCE, not parseability. "Absent" means
    residue (a non-problem); "present but unreadable / truncated /
    malformed" means a CORRUPT install (a real problem the operator must
    see). Collapsing those two into one verdict would let a genuinely
    corrupt install vanish from the report through the same door residue
    leaves by — the exact failure mode that makes people distrust and
    disarm a check. So: ``FileNotFoundError`` disqualifies; ANY other
    ``OSError`` (EACCES, EIO, ELOOP …) still counts, and the contents are
    never parsed here.
    """
    if not path.is_dir():
        return False
    try:
        os.stat(path / "METADATA")
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _dist_info_dirs(
    dist_name: str, search_paths: list[str]
) -> dict[Path, list[Path]]:
    """Map each site dir on ``search_paths`` to the dist-info dirs claiming
    ``dist_name`` inside it. Duplicate path entries are visited once.

    Only entries passing :func:`_is_installed_dist_info` are collected —
    see there for why a name match alone is not evidence of an install.
    """
    canon = _canonical(dist_name)
    suffix = ".dist-info"
    hits: dict[Path, list[Path]] = {}
    seen: set[Path] = set()
    for entry in search_paths:
        try:
            site = Path(entry or ".").resolve()
        except OSError:
            continue
        if site in seen:
            continue
        seen.add(site)
        if not site.is_dir():
            continue
        try:
            children = sorted(site.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.name.endswith(suffix):
                continue
            if not _is_installed_dist_info(child):
                continue
            stem = child.name[: -len(suffix)]
            name_part = stem.rsplit("-", 1)[0] if "-" in stem else stem
            if _canonical(name_part) == canon:
                hits.setdefault(site, []).append(child)
    return hits


def _resolved_dist_info(hits: dict[Path, list[Path]]) -> Path | None:
    """First dist-info in search-path order — the one imports resolve to."""
    for infos in hits.values():
        if infos:
            return infos[0]
    return None


def _integrity_violation(dist_name: str, search_paths: list[str]) -> str | None:
    """INTEGRITY half — purely local; returns a violation message or None.

    Unexpected internal errors return None (the gate must never crash the
    host app with anything but the intended :class:`StalenessError`).
    """
    try:
        hits = _dist_info_dirs(dist_name, search_paths)
        if not _resolved_dist_info(hits):
            return None  # not installed here (e.g. source-tree run) — no verdict
        for site, infos in hits.items():
            if len(infos) > 1:
                names = ", ".join(p.name for p in infos)
                return (
                    f"{dist_name}: ambiguous metadata — {len(infos)} dist-info "
                    f"directories claim it in {site} ({names}).\n"
                    + AMBIGUOUS_METADATA_REMEDY.format(dist=dist_name)
                )
        resolved = _resolved_dist_info(hits)
        dist = Distribution.at(resolved)
        if _editable_dir_from_meta(dist) is not None:
            return None  # editable: RECORD is meaningless; freshness half governs
        # Parse RECORD ourselves, NOT via `dist.files`: Python 3.12's
        # ``Distribution.files`` silently FILTERS OUT entries whose file is
        # absent on disk — which makes the exact corruption this half exists
        # to catch (RECORD-listed file missing) invisible through that API.
        raw_record = dist.read_text("RECORD")
        if raw_record is None:
            return None  # no RECORD (editable-style / legacy) — nothing to verify
        site_root = resolved.parent
        missing: list[str] = []
        for row in csv.reader(io.StringIO(raw_record)):
            if not row or not row[0]:
                continue
            rel = row[0]
            if rel.endswith(".pyc") or "__pycache__" in rel:
                continue  # byte-code may be legitimately cleaned
            try:
                target = Path(rel) if Path(rel).is_absolute() else site_root / rel
                if not target.exists():
                    missing.append(rel)
            except (OSError, ValueError):
                continue
        if missing:
            shown = ", ".join(missing[:5]) + (" …" if len(missing) > 5 else "")
            return (
                f"{dist_name}: partial install — {len(missing)} RECORD-listed "
                f"file(s) missing on disk (e.g. {shown}) — run: "
                f"pip install -U --force-reinstall {dist_name}"
            )
        return None
    except Exception:  # noqa: BLE001 — fail-safe: never crash the host app
        return None


def _cache_dir() -> Path:
    """Per-dist latest-version cache dir. ``$SCITEX_DEV_VERSION_CACHE_DIR``
    overrides (injectable for tests)."""
    override = os.getenv(_ENV_CACHE_DIR)
    if override:
        return Path(override).expanduser()
    try:
        from scitex_config._ecosystem import local_state

        return local_state.path("dev", "runtime", "version-latest")
    except Exception:  # noqa: BLE001 — fail-safe
        return Path.home() / ".scitex" / "dev" / "runtime" / "version-latest"


def _cached_latest_for(dist_name: str) -> tuple[str | None, float]:
    """(latest, fetched_at) from the per-dist cache, else the legacy
    single-file scitex-dev cache, else (None, 0.0). Never raises."""
    canon = _canonical(dist_name)
    path = _cache_dir() / f"{canon}.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        data = None
    if isinstance(data, dict):
        val = data.get("latest") or data.get("version")
        if val:
            try:
                fetched = float(data.get("fetched_at", 0))
            except (TypeError, ValueError):
                fetched = 0.0
            return str(val).strip(), fetched
    if canon == "scitex-dev":
        legacy = _cached_latest(dist_name)
        if legacy:
            return legacy, 0.0  # age unknown → eligible for refresh
    return None, 0.0


_REFRESH_SCRIPT = """\
import json, sys, time, urllib.request
name, out = sys.argv[1], sys.argv[2]
with urllib.request.urlopen(
    "https://pypi.org/pypi/%s/json" % name, timeout=10
) as resp:
    latest = json.load(resp)["info"]["version"]
json.dump({"latest": latest, "fetched_at": time.time()}, open(out, "w"))
"""


def _maybe_refresh_cache(dist_name: str, fetched_at: float) -> None:
    """Opportunistic per-dist cache refresh — detached fire-and-forget child.

    NEVER blocks the invocation path and never raises. Skipped under pytest,
    when ``$SCITEX_DEV_NO_CURRENCY_REFRESH`` is set, when the cache is
    fresh (TTL), or when an attempt was made recently (marker throttle).
    """
    if os.environ.get(_ENV_NO_REFRESH) or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    now = time.time()
    if now - fetched_at < _CACHE_TTL_SECONDS:
        return
    canon = _canonical(dist_name)
    cache_dir = _cache_dir()
    marker = cache_dir / f"{canon}.refresh-attempt"
    try:
        if marker.exists() and now - marker.stat().st_mtime < (
            _REFRESH_MIN_INTERVAL_SECONDS
        ):
            return
        cache_dir.mkdir(parents=True, exist_ok=True)
        marker.touch()
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _REFRESH_SCRIPT,
                dist_name,
                str(cache_dir / f"{canon}.json"),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:  # noqa: BLE001 — refresh is best-effort, never fatal
        pass


def _freshness_message(dist_name: str, search_paths: list[str]) -> str | None:
    """FRESHNESS half — stale message or None. Fail-safe by construction:
    no cache / offline / no upstream / any error → None (PASS)."""
    try:
        dist_info = _resolved_dist_info(_dist_info_dirs(dist_name, search_paths))
        if dist_info is None:
            return None
        dist = Distribution.at(dist_info)
        src = _editable_dir_from_meta(dist)
        if src is not None:
            return _compute_drift(src, distribution=dist_name)
        installed = dist.version
        latest, fetched_at = _cached_latest_for(dist_name)
        _maybe_refresh_cache(dist_name, fetched_at)
        if not installed or not latest:
            return None
        if not _is_older(installed, latest):
            return None
        return (
            f"{dist_name} {installed} is behind latest {latest} — run: "
            f"pip install -U {dist_name}"
        )
    except Exception:  # noqa: BLE001 — fail-safe: never crash the host app
        return None


def _resolve_gate_severity(explicit: str | None) -> str:
    """Explicit arg > $SCITEX_DEV_CURRENCY_SEVERITY > ``currency_severity``
    knob (config.yaml → knob-state.json) > default ``error``."""
    if explicit is not None:
        value = str(explicit).strip().lower()
        if value not in _SEVERITIES:
            raise ValueError(
                f"severity must be one of {_SEVERITIES}, got {explicit!r}"
            )
        return value
    env = os.getenv(_ENV_SEVERITY, "").strip().lower()
    if env in _SEVERITIES:
        return env
    return _resolve_severity(key="currency_severity", default=_DEFAULT_SEVERITY)


def ensure_current(
    dist_name: str,
    *,
    severity: str | None = None,
    _search_paths: list[str] | None = None,
    _halves: tuple[str, ...] = ("integrity", "freshness"),
) -> None:
    """Gate on ``dist_name`` being intact on disk AND current.

    Raises :class:`StalenessError` at ``error`` severity (the default) when a
    violation is found; ``warn`` logs and returns; ``silent`` no-ops. See the
    module docstring for the two halves and the fail-safe rules.

    ``_search_paths`` / ``_halves`` are internal seams (default: ``sys.path``
    and both halves) so tests inject a temp site dir without mocking and the
    scitex-dev CLI can self-check integrity only.
    """
    if os.environ.get(_ENV_BYPASS):
        # An exercised bypass must be VISIBLE, never silent.
        _log_stale(
            "warn",
            f"CURRENCY GATE BYPASSED for {dist_name} ({_ENV_BYPASS}=1) — "
            "integrity + freshness NOT checked; unset the env var to re-arm",
        )
        return
    resolved_severity = _resolve_gate_severity(severity)
    if resolved_severity == "silent":
        return
    paths = list(_search_paths) if _search_paths is not None else list(sys.path)
    problems: list[str] = []
    if "integrity" in _halves:
        violation = _integrity_violation(dist_name, paths)
        if violation:
            problems.append(violation)
    if "freshness" in _halves:
        stale = _freshness_message(dist_name, paths)
        if stale:
            problems.append(stale)
    if not problems:
        return
    text = "; ".join(problems) + f"  ({_SUPPRESS_HINT})"
    if resolved_severity == "error":
        raise StalenessError(text)
    _log_stale("warn", text)


# EOF
