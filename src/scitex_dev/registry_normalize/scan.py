#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure drift-detection engine for ``~/.scitex/<pkg>/`` registry layout.

Single source of truth for "what counts as drift" from the canonical
per-package local-state shape (see
``_skills/general/01_ecosystem/06_dot_scitex_directory.md``)::

    ~/.scitex/<pkg>/
    ├── config.yaml          # ONE config name (or config/ for multi-file)
    ├── runtime/              # ephemeral live state (pids, sockets, locks, ...)
    ├── logs/                 # all *.log
    ├── archive/              # superseded data, as archive/<UTC>/ subdirs
    ├── bin/ , scripts/        # package-shipped exec/scripts
    └── <domain>/             # authored content (agents/, decisions/, ...)

Both the PS-181 audit rule (``_cli/audit/_project/_check_registry_layout.py``)
and the ``scitex-dev registry-normalize`` CLI tool call ``scan_pkg_dir`` /
``scan_registry`` below — detection logic lives in exactly one place so the
two surfaces can never drift apart.

Scope discipline (mirrors the spec): only the TOP LEVEL of
``~/.scitex/<pkg>/`` is inspected, plus one level into a directory that
looks like a venv (checking for ``pyvenv.cfg``). Anything inside a
domain-authored or already-canonical subdirectory (``agents/``,
``decisions/``, ``docs/``, ``tokens/``, ``accounts/``, ``tasks/``,
``config/``, ``runtime/``, ``logs/``, ``archive/``, ``bin/``,
``scripts/``, ``venvs/``) is never recursed into and never flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Kinds that the registry-normalize CLI tool will auto-move (dry-run by
# default; see registry_normalize/normalize.py). Kinds NOT in this set
# (config-both, config-wrong-name, build-artifact, venv-wrong-name) are
# audit-only — see the PR description for why (renaming a config file or
# a venv is not a mechanical/safe move; __pycache__ is a delete, not a
# move, and this tool never deletes).
MOVABLE_KINDS = frozenset(
    {
        "loose-log",
        "loose-runtime-state",
        "archive-dir-naming",
        "bak-file-naming",
        "loose-script",
    }
)

# Config-shaped file at top level: only .yaml/.yml — the canonical name is
# `config.yaml` exactly; anything else with a config-like extension is its
# own violation regardless of whether config.yaml/config/ already exists.
_CONFIG_SHAPED_RE = re.compile(r"^[\w.-]+\.(yaml|yml)$")

# `_archive-<8-digit-date>` directory shape, e.g. `_archive-20260617`.
_ARCHIVE_DATE_DIR_RE = re.compile(r"^_archive-(\d{8})$")

# `*.bak-<8-digit-date>` file shape, e.g. `tasks.yaml.bak-20260601`.
_BAK_DATE_FILE_RE = re.compile(r"^(.+)\.bak-(\d{8})$")

# Loose runtime-state files: *.pid / *.sock / *.state / *_latest.json /
# the exact name `ci-state.json`.
_PID_SOCK_STATE_RE = re.compile(r"^.+\.(pid|sock|state)$")
_LATEST_JSON_RE = re.compile(r"^.+_latest\.json$")

_LOG_FILE_RE = re.compile(r"^.+\.log$")
_PY_SH_FILE_RE = re.compile(r"^.+\.(py|sh)$")

_BUILD_ARTIFACT_DIR_NAMES = frozenset({"__pycache__"})

_CANONICAL_TOP_NAME = "config.yaml"
_CANONICAL_VENV_DIR = "venvs"


@dataclass(frozen=True)
class DriftItem:
    """One (pkg, drift-instance) finding.

    ``dest`` is the canonical location relative to the package's
    ``~/.scitex/<pkg>/`` root — ``None`` when there is no single
    mechanical destination (e.g. config-naming drift).
    """

    pkg: str
    kind: str
    path: str
    detail: str
    dest: str | None = None


def _is_runtime_state_file(name: str) -> bool:
    return bool(
        _PID_SOCK_STATE_RE.match(name)
        or _LATEST_JSON_RE.match(name)
        or name == "ci-state.json"
    )


def scan_pkg_dir(pkg_dir: Path) -> list[DriftItem]:
    """Return every drift instance found at the top level of *pkg_dir*.

    *pkg_dir* is a single ``~/.scitex/<pkg>/`` directory (already
    resolved by the caller — this function does no `$SCITEX_DIR`
    resolution of its own, keeping it trivially unit-testable against
    any ``tmp_path``).
    """
    pkg = pkg_dir.name
    items: list[DriftItem] = []

    # 1. config.yaml XOR config/ — both present is its own violation.
    has_config_yaml = (pkg_dir / "config.yaml").is_file()
    has_config_dir = (pkg_dir / "config").is_dir()
    if has_config_yaml and has_config_dir:
        items.append(
            DriftItem(
                pkg,
                "config-both",
                str(pkg_dir / "config.yaml"),
                (
                    "both `config.yaml` and `config/` exist at top level — "
                    "pick ONE canonical config location (a single "
                    "`config.yaml`, or `config/` for multi-file config); "
                    "having both invites drift between them."
                ),
            )
        )

    entries = sorted(pkg_dir.iterdir(), key=lambda p: p.name)

    for entry in entries:
        name = entry.name
        if entry.is_file():
            if _CONFIG_SHAPED_RE.match(name) and name != _CANONICAL_TOP_NAME:
                items.append(
                    DriftItem(
                        pkg,
                        "config-wrong-name",
                        str(entry),
                        (
                            f"`{name}` is a config-shaped file at top level "
                            f"but not the canonical name — rename to "
                            f"`{_CANONICAL_TOP_NAME}` (or move multi-file "
                            f"config under `config/`)."
                        ),
                    )
                )
                continue
            m_bak = _BAK_DATE_FILE_RE.match(name)
            if m_bak:
                date = m_bak.group(2)
                dest = f"archive/{date}/{name}"
                items.append(
                    DriftItem(
                        pkg,
                        "bak-file-naming",
                        str(entry),
                        (
                            f"`{name}` is a dated backup file at top level "
                            f"— move to `{dest}`."
                        ),
                        dest=dest,
                    )
                )
                continue
            if _LOG_FILE_RE.match(name):
                dest = f"logs/{name}"
                items.append(
                    DriftItem(
                        pkg,
                        "loose-log",
                        str(entry),
                        (
                            f"`{name}` is a loose log file at top level — "
                            f"move to `{dest}`."
                        ),
                        dest=dest,
                    )
                )
                continue
            if _is_runtime_state_file(name):
                dest = f"runtime/{name}"
                items.append(
                    DriftItem(
                        pkg,
                        "loose-runtime-state",
                        str(entry),
                        (
                            f"`{name}` is ephemeral runtime state at top "
                            f"level — move to `{dest}`."
                        ),
                        dest=dest,
                    )
                )
                continue
            if _PY_SH_FILE_RE.match(name):
                dest = f"scripts/{name}"
                items.append(
                    DriftItem(
                        pkg,
                        "loose-script",
                        str(entry),
                        (
                            f"`{name}` is a loose script at top level — "
                            f"move to `{dest}` (or `bin/{name}` if it is "
                            f"an installed executable)."
                        ),
                        dest=dest,
                    )
                )
                continue
        elif entry.is_dir():
            if name in _BUILD_ARTIFACT_DIR_NAMES:
                items.append(
                    DriftItem(
                        pkg,
                        "build-artifact",
                        str(entry),
                        (
                            f"`{name}/` is a build/editor artifact at top "
                            f"level of the registry state dir — it should "
                            f"never be created there; safe to delete."
                        ),
                    )
                )
                continue
            m_arch = _ARCHIVE_DATE_DIR_RE.match(name)
            if m_arch:
                date = m_arch.group(1)
                dest = f"archive/{date}"
                items.append(
                    DriftItem(
                        pkg,
                        "archive-dir-naming",
                        str(entry),
                        (
                            f"`{name}/` looks like a superseded snapshot "
                            f"but sits at top level — move to `{dest}/`."
                        ),
                        dest=dest,
                    )
                )
                continue
            # Venv detection: ONLY via presence of pyvenv.cfg directly
            # inside, to avoid false positives on arbitrary directories.
            if name != _CANONICAL_VENV_DIR and (entry / "pyvenv.cfg").is_file():
                dest = f"{_CANONICAL_VENV_DIR}/{name}"
                items.append(
                    DriftItem(
                        pkg,
                        "venv-wrong-name",
                        str(entry),
                        (
                            f"`{name}/` is a virtualenv (has `pyvenv.cfg`) "
                            f"but the canonical name is "
                            f"`{_CANONICAL_VENV_DIR}/` — move it to "
                            f"`{dest}/`."
                        ),
                    )
                )
                continue
            # Any other directory (domain-authored content, already-
            # canonical dirs, or an unrecognized dir with no pyvenv.cfg
            # inside) is intentionally never flagged, and never recursed
            # into — see module docstring "Scope discipline".

    return items


def scan_registry(scitex_dir: Path) -> dict[str, list[DriftItem]]:
    """Scan every ``<pkg>/`` subdirectory under *scitex_dir*.

    Returns ``{pkg_name: [DriftItem, ...]}`` — packages with zero drift
    are omitted from the result.
    """
    out: dict[str, list[DriftItem]] = {}
    if not scitex_dir.is_dir():
        return out
    for pkg_dir in sorted(scitex_dir.iterdir(), key=lambda p: p.name):
        if not pkg_dir.is_dir():
            continue
        if pkg_dir.name.startswith("."):
            continue
        items = scan_pkg_dir(pkg_dir)
        if items:
            out[pkg_dir.name] = items
    return out


# EOF
