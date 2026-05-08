"""PS150 / PS151 — scitex-dev pin enforcement.

Symptom these prevent: a package's `tests/develop/test_audit.py`
calls `shutil.which("scitex-dev")` and `pytest.skip()`s when absent.
A consumer pyproject.toml that does NOT declare `scitex-dev` in
`[project.optional-dependencies.dev]` (or in `[project.dependencies]`
for runtime tooling) silently has NO audit gate in CI's fresh venv.

PS150 (W) — `scitex-dev` (or `scitex-dev[cli-audit]`) absent from
            both `[project.dependencies]` and `[project.optional-
            dependencies.dev]`. Audit gate silently skipped.

PS151 (W) — `scitex-dev` is declared but the version pin floor is
            below the known-good version (`MIN_KNOWN_GOOD`).
            Older scitex-dev releases ship a smaller / differently-
            classified rule corpus, so the same package gets
            different audit verdicts depending on which scitex-dev
            wheel PyPI happens to surface.

Both severities are W initially so the rule rolls out without
breaking CI on consumer packages. Promote to E once the ecosystem-
wide pin sweep lands.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Bump in lockstep with each scitex-dev release that meaningfully
# changes the rule corpus (e.g. promotes a W to E, or adds a rule).
MIN_KNOWN_GOOD = "0.11.5"

_DEV_BLOCK_RE = re.compile(r"^dev\s*=\s*\[(.*?)^\]", re.MULTILINE | re.DOTALL)
_RUNTIME_BLOCK_RE = re.compile(
    r"^dependencies\s*=\s*\[(.*?)^\]", re.MULTILINE | re.DOTALL
)
_PIN_RE = re.compile(r'"scitex-dev(?:\[[^\]]*\])?(?:>=([0-9][0-9.]*))?"')


def _version_lt(a: str, b: str) -> bool:
    """Return True if version a < b. Loose semver tuple compare."""
    try:
        return tuple(int(x) for x in a.split(".")) < tuple(int(x) for x in b.split("."))
    except ValueError:
        return False  # non-numeric pre-release — treat as ok


def check_audit_pin(repo: Path, Violation: type, out: list[Any]) -> None:
    """Wire into the project auditor."""
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return
    txt = pyproject.read_text(errors="ignore")

    rt = _RUNTIME_BLOCK_RE.search(txt)
    dv = _DEV_BLOCK_RE.search(txt)
    rt_pins = _PIN_RE.findall(rt.group(1)) if rt else []
    dv_pins = _PIN_RE.findall(dv.group(1)) if dv else []
    all_pins = rt_pins + dv_pins

    if not all_pins:
        out.append(
            Violation(
                "PS150",
                str(pyproject),
                (
                    "[dev] does not declare `scitex-dev` — "
                    "tests/develop/test_audit.py silently skips in a "
                    f'fresh venv. Add `"scitex-dev>={MIN_KNOWN_GOOD}"` '
                    "to `[project.optional-dependencies.dev]`."
                ),
            )
        )
        return

    # Find the floor across all pin declarations. Bare `scitex-dev`
    # (no >=N) means floats — flag with PS151 too because that's
    # exactly the drift the rule fights.
    floors = [p for p in all_pins if p]
    if not floors:
        out.append(
            Violation(
                "PS151",
                str(pyproject),
                (
                    "scitex-dev declared without a version floor. Pin to "
                    f"`scitex-dev>={MIN_KNOWN_GOOD}` so the audit corpus "
                    "is reproducible across the ecosystem."
                ),
            )
        )
        return

    lowest = min(
        floors, key=lambda v: tuple(int(x) for x in v.split(".") if x.isdigit())
    )
    if _version_lt(lowest, MIN_KNOWN_GOOD):
        out.append(
            Violation(
                "PS151",
                str(pyproject),
                (
                    f"scitex-dev pin floor {lowest!r} is below the "
                    f"known-good version {MIN_KNOWN_GOOD!r}. Older "
                    "scitex-dev ships a smaller rule corpus → different "
                    "verdicts across the ecosystem. Bump the floor."
                ),
            )
        )
