#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared fixtures for the scitex_dev test tree.

``installed_job_provider`` registers a *real* ``scitex_dev.jobs``
entry-point provider (a temporary installed distribution on ``sys.path``)
so ``discover_jobs()`` finds it through the exact ``importlib.metadata``
path used in production — no ``monkeypatch``, no mock.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

_PROVIDER_SRC = textwrap.dedent(
    """
    from scitex_dev.jobs import JobSpec

    def provide():
        return [
            JobSpec(
                name="testpkg.sysjob",
                kind="timer",
                schedule="0 */4 * * *",
                command="testpkg go",
                description="test systemd timer job",
                on_boot_sec="15min",
                on_unit_active_sec="4h",
                timeout_sec=99,
            ),
            JobSpec(
                name="testpkg.svc",
                kind="service",
                schedule="",
                command="echo testpkg-service",
                description="test long-running service job",
                on_boot_sec="15s",
                restart_policy="on-failure",
            ),
        ]
"""
)


@pytest.fixture
def installed_job_provider():
    """Yield after installing a real ``scitex_dev.jobs`` entry-point provider."""
    root = Path(tempfile.mkdtemp(prefix="jobsprov-"))
    (root / "jprov.py").write_text(_PROVIDER_SRC, encoding="utf-8")
    dist_info = root / "jprov-0.0.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: jprov\nVersion: 0.0.0\n", encoding="utf-8"
    )
    (dist_info / "entry_points.txt").write_text(
        "[scitex_dev.jobs]\njprov = jprov:provide\n", encoding="utf-8"
    )
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    try:
        yield
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(str(root))
        sys.modules.pop("jprov", None)
        importlib.invalidate_caches()


# EOF
