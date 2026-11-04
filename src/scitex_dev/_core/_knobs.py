#!/usr/bin/env python3
# File: scitex_dev/_core/_knobs.py

"""Machine-managed per-package knob-state (skills / mcp / cli / test-execution).

The CLI and aggregators toggle a package's knobs here; the hand-authored
``config.yaml`` is never rewritten. Keeping the two apart means toggling a knob
can never clobber the operator's config comments, and a diff of the state file
shows exactly which packages were deliberately changed.

Two value shapes share the one JSON file:
  * ``skills`` / ``mcp`` / ``cli`` — booleans (surface this package into context or not).
  * ``test_execution`` — a mode string (``"local"`` / ``"remote-required"``),
    resolved with the same ECOSYSTEM → config.yaml → knob-state precedence.

Extracted from ``config.py`` (which exceeded the line budget); ``config.py``
re-exports these names so existing imports keep working.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from scitex_config._ecosystem import local_state

from .names import normalize_distribution_name
from .test_execution import DEFAULT_MODE, TEST_EXECUTION_MODES

if TYPE_CHECKING:
    from .config import PackageConfig

_KNOB_KINDS = ("skills", "mcp", "cli")


def _knob_state_path() -> Path:
    """Machine-managed knob-state file (``~/.scitex/dev/runtime/knob-state.json``).

    ``$SCITEX_DEV_KNOB_STATE`` overrides the location (injectable for tests).
    """
    override = os.getenv("SCITEX_DEV_KNOB_STATE")
    if override:
        return Path(override).expanduser()
    return local_state.path("dev", "runtime", "knob-state.json")


def _empty_state() -> dict[str, dict]:
    return {"skills": {}, "mcp": {}, "cli": {}, "test_execution": {}}


def _load_knob_state(
    path: Path | None = None, *, strict: bool = False
) -> dict[str, dict]:
    """Load the knob-state file, tolerating absence / corruption (default: empty).

    ``path`` defaults to :func:`_knob_state_path`; it is injectable so callers
    (and tests) never need env vars or mocks.
    """
    if path is None:
        path = _knob_state_path()
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return _empty_state()
    except (json.JSONDecodeError, OSError) as exc:
        if strict:
            raise ValueError("cannot read exposure knob state") from exc
        return _empty_state()
    if not isinstance(data, dict):
        raise TypeError("exposure knob state must be an object")
    if strict and any(
        not isinstance(data.get(kind, {}), dict)
        for kind in (*_KNOB_KINDS, "test_execution")
    ):
        raise TypeError("exposure knob groups must be objects")
    return {
        "skills": dict(data.get("skills", {})),
        "mcp": dict(data.get("mcp", {})),
        "cli": dict(data.get("cli", {})),
        "test_execution": dict(data.get("test_execution", {})),
    }


def _apply_knob_state(
    packages: list[PackageConfig], path: Path | None = None, *, state=None
) -> None:
    """Overlay the machine-managed knob-state (highest precedence) in place."""
    state = _load_knob_state(path) if state is None else state
    skills, mcp, texec = (
        state["skills"],
        state["mcp"],
        state["test_execution"],
    )
    for p in packages:
        if p.name in skills:
            p.skills_enabled = bool(skills[p.name])
        if p.name in mcp:
            p.mcp_enabled = bool(mcp[p.name])
        if p.name in state["cli"]:
            p.cli_enabled = _cli_bool(state["cli"][p.name])
        if p.name in texec:
            p.test_execution = str(texec[p.name])


def set_package_knob(
    name: str, kind: str, enabled: bool, path: Path | None = None
) -> Path:
    """Persist a per-package skills/mcp/cli knob to the machine-managed state file.

    ``kind`` is ``"skills"``, ``"mcp"`` or ``"cli"``. ``path`` defaults to
    :func:`_knob_state_path` (injectable for tests). Returns the state-file path.
    The hand-authored ``config.yaml`` is never touched.
    """
    if kind not in _KNOB_KINDS:
        raise ValueError(f"kind must be one of {_KNOB_KINDS}, got {kind!r}")
    if kind == "cli":
        name = normalize_distribution_name(name)
        enabled = _cli_bool(enabled)
    if path is None:
        path = _knob_state_path()
    state = _load_knob_state(path, strict=kind == "cli")
    if kind == "cli":
        state["cli"] = _canonical_surface_state(state)["cli"]
    state[kind][name] = bool(enabled)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return path


def set_package_test_execution(name: str, mode: str, path: Path | None = None) -> Path:
    """Persist a per-package test-execution MODE to the knob-state file.

    ``mode`` must be one of :data:`TEST_EXECUTION_MODES`. Mirrors
    :func:`set_package_knob` but for the string-valued test-execution knob.
    """
    if mode not in TEST_EXECUTION_MODES:
        raise ValueError(f"mode must be one of {TEST_EXECUTION_MODES}, got {mode!r}")
    if path is None:
        path = _knob_state_path()
    state = _load_knob_state(path)
    state["test_execution"][name] = str(mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return path


# Kept for callers that imported the default from config; re-exported there.
DEFAULT_TEST_EXECUTION_MODE = DEFAULT_MODE


# EOF


def _cli_bool(value) -> bool:
    """CLI preferences require real booleans, never truthy strings."""
    if not isinstance(value, bool):
        raise TypeError("cli_enabled must be a boolean")
    return value


def _canonical_surface_state(state):
    result = dict(state)
    for kind in _KNOB_KINDS:
        result[kind] = {}
        for name, value in state[kind].items():
            owner = normalize_distribution_name(name)
            if not isinstance(value, bool):
                raise TypeError(f"{kind} preference must be a boolean")
            if owner in result[kind] and result[kind][owner] != value:
                raise ValueError("conflicting canonical owner preferences")
            result[kind][owner] = value
    return result
