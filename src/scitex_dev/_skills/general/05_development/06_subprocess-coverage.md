---
description: |
  [TOPIC] Subprocess coverage wiring (parallel + COVERAGE_PROCESS_START)
  [DETAILS] Configure independent coverage files and a shared configuration for child Python interpreters. Check installed startup support; use a single-line .pth binding where needed. Verify real child lines and data combination rather than assuming that a coverage or pytest-cov installation provides them.
tags: [scitex-general-package-subprocess-coverage]
---

# Subprocess coverage wiring

## When this matters

If your test suite ever spawns a child Python interpreter — e.g.:

- `subprocess.run([sys.executable, "-m", "pkg.module"], ...)` (demo smoke tests)
- `jupyter nbconvert --execute notebook.ipynb` (PS-505 example tests)
- `pytest-xdist` parallel workers (multiple worker processes)

Child interpreters need startup instrumentation and an appropriate data path.
Some coverage versions provide their own startup binding; environments without
one need the fallback below. Active children also need separate data files:
without parallel mode, concurrent SQLite writes can collide.

Symptom: coverage stays mysteriously low despite covering "everything" in
tests; ~1500 LOC of `_demo_*.py` modules report 0% even when smoke tests
execute them end-to-end.

## The three-part fix

### 1. pyproject.toml `[tool.coverage.run]`

```toml
[tool.coverage.run]
parallel = true
source = ["<import_name>"]
concurrency = ["multiprocessing", "thread"]
```

- `parallel = true` makes every coverage process write to its own
  `.coverage.<hostname>.<pid>.<random>` file (instead of all writing to
  one and racing).
- `concurrency = ["multiprocessing", "thread"]` supports those worker types;
  startup instrumentation covers independent Python subprocesses.
- With pytest-cov collection enabled, the plugin combines data and emits the
  requested reports. A plain pytest run still needs an explicit combination.

### 2. tests/conftest.py — FORCE-SET, not setdefault

```python
"""Module-import-time coverage wiring (parallel + subprocess support).

`os.environ.setdefault` would be a no-op here because pytest-cov has
already set COVERAGE_FILE to a tmp dir by the time conftest is loaded.
"""
from __future__ import annotations

import os
import sys
import sysconfig
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Pin coverage's data file at the repo root and point process_startup
# at our pyproject so child interpreters configure themselves correctly.
os.environ["COVERAGE_PROCESS_START"] = str(_PROJECT_ROOT / "pyproject.toml")
os.environ["COVERAGE_FILE"] = str(_PROJECT_ROOT / ".coverage")


def _ensure_subprocess_coverage_shim() -> None:
    """Drop an idempotent `.pth` file in site-packages that auto-starts
    coverage in every child Python interpreter via
    `coverage.process_startup()`.
    """
    purelib = Path(sysconfig.get_paths()["purelib"])
    pth = purelib / "_<import_name>_subprocess_coverage.pth"
    shim = (
        "import os; os.environ.get('COVERAGE_PROCESS_START') and "
        "__import__('coverage').process_startup()\n"
    )
    try:
        if not pth.exists() or pth.read_text() != shim:
            pth.write_text(shim)
    except OSError:
        # site-packages may be read-only (e.g. system Python); silently
        # skip — local dev venvs are writable and that's where this matters.
        pass


_ensure_subprocess_coverage_shim()
```

Critical detail: **force-set, not `setdefault`**. `pytest-cov` sets
`COVERAGE_FILE` before `conftest.py` runs, so `setdefault` is a silent
no-op and the fix appears to "do nothing" — a classic foot-gun.

An executable `.pth` entry must occupy one physical line beginning with
`import`. A separate `if` line is treated as a path, so its indented body never
runs. The binding above starts tracing during site initialization when the
configuration variable is present. Coverage's startup guard handles repeated
calls when its own installed binding also runs.

The checkout-root data path assumes an isolated test worktree. Coordinate any
deliberate caller-owned data directory with the combine step rather than
overwriting another run's location.

`tests/integration/test_documented_coverage_startup.py` exercises this exact
literal binding in an owned site directory with other startup bindings
disabled, then checks actual child coverage lines. It does not qualify every
installed environment or execute arbitrary documentation fences.

### 3. (Optional) .coveragerc fallback

If you don't want pyproject-based config, the same can live in
`.coveragerc`:

```ini
[run]
parallel = True
source = <import_name>
concurrency = multiprocessing,thread
```

`COVERAGE_PROCESS_START` will pick up whichever file path you point at.

## Verifying it works

Run the suite locally:

```bash
pytest -x
ls .coverage.*  # should show several .coverage.<host>.<pid> shards
coverage combine
coverage report  # should now include subprocess-only LOC
```

Before the wiring, `.coverage.*` shards are absent (children don't write)
and demo modules show 0% even though `test_demos.py` executed them.

## CI side: nothing extra

When collection is enabled with pytest-cov, it combines data and emits the
requested report. Keep the uploader pointed at that verified report; inspect
child-only lines rather than treating upload success as coverage acceptance.

## Gotchas

- **`COVERAGE_FILE` pinned to repo root, not tmp.** If you point it at a
  tmp dir, the per-test shards land somewhere `coverage combine` won't
  find them. Repo root is canonical.
- **Shim must be idempotent.** Test reruns will overwrite the `.pth`
  file every time without the `if not pth.exists() or pth.read_text() != shim`
  guard — minor but it adds noise to `pip list -v` output.
- **site-packages may be read-only.** Catch `OSError` and continue;
  system-Python users can't write the shim, but in practice everyone
  runs tests from a venv they own.
- **Check the installed coverage version.** Declare `coverage>=7.0` in the
  development profile used for this workflow. Do not assume a pytest-cov
  version alone guarantees that lower bound or a working startup binding.

## Related skills

- `02_package/11_ci-and-codecov.md` — overall CI / codecov.yml setup.
- `05_development/07_demo-smoke-tests.md` — the demo smoke test pattern
  that this wiring exists to instrument.
- `01_ecosystem/02_dependency-and-version-pinning.md` — `[dev]` extras
  completeness rule (the reason `nbconvert` / `ipykernel` go in `[dev]`).
