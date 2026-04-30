#!/usr/bin/env python3.11
"""Enforce AGPL-3.0-only licensing across the SciTeX ecosystem.

Canonical tool — the scitex-python mirror under `scripts/` was removed
in favour of this one (per the two-path drift rule in the quality
checklist: single source, canonical home in scitex-dev).

Every in-scope repo must have, consistently:

  1. `pyproject.toml` with `license = "AGPL-3.0-only"` (PEP 639 SPDX form).
     `AGPL-3.0` (deprecated form) is rejected.
  2. **No legacy `License :: OSI Approved :: ...` classifier alongside SPDX.**
     Setuptools >=80 hard-rejects the combination per PEP 639. The
     classifier must be absent when `license = "AGPL-3.0-only"` is set.
  3. `LICENSE` file at repo root containing AGPL v3 full text.

Scope: `pyproject.toml` exists AND directory-name equals pyproject
`name` AND (name starts with `scitex-` / equals `scitex` / is on the
allowlist).

Usage:
    python3.11 scripts/quality/audit_license.py
    python3.11 scripts/quality/audit_license.py --projects-root ~/proj
    python3.11 scripts/quality/audit_license.py --format github
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ECOSYSTEM_ALLOWLIST = {
    "figrecipe",
    "socialia",
    "openalex-local",
    "crossref-local",
}

EXPECTED_LICENSE = "AGPL-3.0-only"
# PEP 639: setuptools >=80 hard-rejects this classifier when SPDX
# `license = ...` is also set. Now flagged as a violation if PRESENT.
LEGACY_CLASSIFIER_PREFIX = "License :: OSI Approved"
AGPL_SIGNATURE = "GNU AFFERO GENERAL PUBLIC LICENSE"


def _pyproject_name(p: Path) -> str | None:
    f = p / "pyproject.toml"
    if not f.is_file():
        return None
    m = re.search(r'^name\s*=\s*"([^"]+)"', f.read_text(), re.MULTILINE)
    return m.group(1) if m else None


def in_scope(p: Path) -> bool:
    name = _pyproject_name(p)
    if name is None or name != p.name:
        return False
    return name.startswith("scitex-") or name == "scitex" or name in ECOSYSTEM_ALLOWLIST


def check_repo(repo: Path) -> list[str]:
    """Return list of violation messages, empty if compliant."""
    v: list[str] = []
    py = repo / "pyproject.toml"
    txt = py.read_text(encoding="utf-8")

    m = re.search(r'^license\s*=\s*"([^"]+)"', txt, re.MULTILINE)
    if not m:
        if re.search(r"^license\s*=\s*\{", txt, re.MULTILINE):
            v.append(
                "pyproject license uses dict form; prefer "
                f'`license = "{EXPECTED_LICENSE}"` (PEP 639 SPDX)'
            )
        else:
            v.append("pyproject.toml has no `license = ...` line")
    elif m.group(1) != EXPECTED_LICENSE:
        v.append(
            f'pyproject license is "{m.group(1)}"; expected '
            f'"{EXPECTED_LICENSE}" (SPDX; `AGPL-3.0` is deprecated)'
        )

    # PEP 639: legacy AGPL trove classifier alongside SPDX `license = ...`
    # is rejected by setuptools >=80. Flag its PRESENCE as a violation.
    legacy_classifier_re = re.compile(
        r'^\s*"License :: OSI Approved :: GNU Affero[^"]*"', re.MULTILINE
    )
    if legacy_classifier_re.search(txt):
        v.append(
            "legacy `License :: OSI Approved :: ...` classifier present "
            "alongside SPDX license — setuptools >=80 will reject the build (PEP 639)"
        )

    lf = repo / "LICENSE"
    if not lf.is_file():
        v.append("LICENSE file missing at repo root")
    else:
        head = lf.read_text(encoding="utf-8", errors="replace")[:500]
        if AGPL_SIGNATURE not in head.upper():
            v.append(f"LICENSE file present but does not contain '{AGPL_SIGNATURE}'")

    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects-root", type=Path, default=Path.home() / "proj")
    ap.add_argument("--format", choices=["plain", "github"], default="plain")
    args = ap.parse_args()

    any_fail = False
    total = 0
    offenders = 0

    for d in sorted(args.projects_root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if not in_scope(d):
            continue
        total += 1
        violations = check_repo(d)
        if violations:
            any_fail = True
            offenders += 1
            print(f"\n[{d.name}]")
            for msg in violations:
                if args.format == "github":
                    print(
                        f"::error file={d / 'pyproject.toml'}::license/{d.name}: {msg}"
                    )
                else:
                    print(f"  - {msg}")

    print()
    if any_fail:
        print(
            f"FAIL — {offenders}/{total} ecosystem packages have license "
            f"inconsistencies. Expected everywhere:\n"
            f'  pyproject.toml:  license = "{EXPECTED_LICENSE}"\n'
            f"  classifier:      (no legacy `License :: OSI Approved :: ...` — PEP 639)\n"
            f"  LICENSE file:    AGPL v3 full text at repo root\n"
            f"\nRun `python3.11 scripts/quality/fix_license.py --apply` "
            f"to auto-fix clean-tree repos."
        )
        return 1

    print(f"PASS — {total}/{total} ecosystem packages AGPL-3.0-only clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
