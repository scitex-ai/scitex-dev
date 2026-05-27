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
