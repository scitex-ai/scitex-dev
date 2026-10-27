#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The `disk-guard` cron body.

The property that matters most here is the one that is easy to lose in
a refactor: INSTALLING THIS JOB ARMS NOTHING. The body runs, measures
the host, prints what it saw, and deletes nothing until the host opts
in on the config surface.
"""

from __future__ import annotations

import io
from pathlib import Path

from scitex_dev._cli.cron import _disk_guard


def _run_with_home(home: Path) -> tuple[str, _disk_guard.DiskGuardRunResult]:
    import os

    saved = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    sink = io.StringIO()
    try:
        result = _disk_guard.run_once(out=sink)
    finally:
        if saved is None:
            del os.environ["HOME"]
        else:
            os.environ["HOME"] = saved
    return sink.getvalue(), result


def test_unarmed_host_reports_off_and_deletes_nothing(tmp_path):
    out, result = _run_with_home(tmp_path / "bare")
    assert result.failed is False
    assert result.deleted == 0
    assert "off" in out


def test_armed_but_fully_protected_deletes_nothing(tmp_path):
    home = tmp_path / "armed"
    config = home / ".scitex" / "dev" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "cleanup:\n  disk:\n    enabled: true\n    protect:\n      - '*'\n"
    )
    out, result = _run_with_home(home)
    assert result.failed is False
    assert result.deleted == 0
    assert "kept" in out or "deleted (0 B freed)" in out


# EOF
