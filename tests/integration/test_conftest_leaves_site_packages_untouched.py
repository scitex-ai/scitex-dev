"""Importing tests/conftest.py must leave site-packages and coverage env alone.

WHY THIS EXISTS. conftest.py used to install a ``*_subprocess_coverage.pth``
hook into the interpreter's site-packages at import time and force-set
``COVERAGE_PROCESS_START`` / ``COVERAGE_FILE``. The hook stayed behind and
ran at every later Python start of that environment. Subprocess coverage is
now configured declaratively via coverage.py's subprocess patch
(``patch = ["subprocess"]`` in pyproject.toml), so collection must not write
.pth files or overwrite caller-owned coverage environment variables.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"

_CHILD_CODE = (
    "import os\n"
    "import runpy\n"
    "import site\n"
    "\n"
    "os.environ['COVERAGE_PROCESS_START'] = 'conftest-regression-sentinel-start'\n"
    "os.environ['COVERAGE_FILE'] = 'conftest-regression-sentinel-file'\n"
    "\n"
    "\n"
    "def _snapshot():\n"
    "    snapshot = {}\n"
    "    dirs = []\n"
    "    try:\n"
    "        dirs.extend(site.getsitepackages())\n"
    "    except Exception:\n"
    "        pass\n"
    "    try:\n"
    "        dirs.append(site.getusersitepackages())\n"
    "    except Exception:\n"
    "        pass\n"
    "    for directory in dirs:\n"
    "        try:\n"
    "            names = sorted(os.listdir(directory))\n"
    "        except OSError:\n"
    "            continue\n"
    "        snapshot[directory] = names\n"
    "    return snapshot\n"
    "\n"
    "\n"
    "before = _snapshot()\n"
    "runpy.run_path(%r)\n"
    "after = _snapshot()\n"
    "assert before == after, (\n"
    "    'conftest changed site-packages contents: '\n"
    "    f'{sorted(set(after) - set(before))} '\n"
    "    f'{[d for d in before if before[d] != after.get(d)]}'\n"
    ")\n"
    "assert os.environ.get('COVERAGE_PROCESS_START') == (\n"
    "    'conftest-regression-sentinel-start'\n"
    ")\n"
    "assert os.environ.get('COVERAGE_FILE') == 'conftest-regression-sentinel-file'\n"
) % str(CONFTEST)


def test_conftest_leaves_site_packages_untouched():
    # Arrange
    assert CONFTEST.is_file(), f"conftest not found at {CONFTEST}"
    # Act
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_CODE],
        capture_output=True,
        text=True,
    )
    # Assert
    assert completed.returncode == 0, (
        f"child failed with exit {completed.returncode}\n"
        f"--- stdout ---\n{completed.stdout}\n"
        f"--- stderr ---\n{completed.stderr}"
    )
