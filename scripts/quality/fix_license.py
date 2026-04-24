#!/usr/bin/env python3.11
"""Auto-fix AGPL-3.0-only licensing across the SciTeX ecosystem.

Paired with `audit_license.py`. Dry-run by default; pass `--apply` to
write changes.

For each in-scope repo with a clean working tree (no uncommitted
changes), this tool will:

  1. Rewrite `pyproject.toml` `license = "AGPL-3.0"` → `"AGPL-3.0-only"`
     (PEP 639 SPDX modernization).
  2. Insert the AGPL classifier into `[project].classifiers` if missing.
  3. Copy a canonical LICENSE file from a reference repo if missing.

**Dirty repos are skipped.** Never touches a repo that has uncommitted
user work; those are reported with the exact file paths to apply
manually. The scitex-python `99_scitex-quality-checklist.md` §12
dirty-tree rule is enforced.

Usage:
    python3.11 scripts/quality/fix_license.py                 # dry run
    python3.11 scripts/quality/fix_license.py --apply         # write
    python3.11 scripts/quality/fix_license.py --apply --commit  # + commit per repo via git_guard_commit.sh

Commit path uses `~/.claude/to_claude/bin/git_guard_commit.sh` to
guarantee the commit contains ONLY the files this script touched.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# Reuse the auditor's scope + expectations.
from audit_license import (  # type: ignore
    AGPL_SIGNATURE,
    EXPECTED_CLASSIFIER,
    EXPECTED_LICENSE,
    check_repo,
    in_scope,
)

REFERENCE_LICENSE_CANDIDATES = (
    "scitex-plt",
    "scitex-io",
    "scitex-stats",
    "scitex-dev",
)
GUARD_SCRIPT = Path.home() / ".claude/to_claude/bin/git_guard_commit.sh"


def _canonical_license_text(projects_root: Path) -> str:
    """Find an AGPL v3 full-text LICENSE file to use as the template."""
    for cand in REFERENCE_LICENSE_CANDIDATES:
        lf = projects_root / cand / "LICENSE"
        if lf.is_file():
            head = lf.read_text(encoding="utf-8", errors="replace")[:500]
            if AGPL_SIGNATURE in head.upper():
                return lf.read_text(encoding="utf-8")
    raise RuntimeError(
        f"No AGPL LICENSE template found in {REFERENCE_LICENSE_CANDIDATES}"
    )


def _is_dirty(repo: Path) -> bool:
    r = subprocess.run(
        ["git", "-C", str(repo), "status", "--short"],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(r.stdout.strip())


def _fix_spdx(text: str) -> str:
    return re.sub(
        r'^(license\s*=\s*)"AGPL-3\.0"',
        r'\1"' + EXPECTED_LICENSE + '"',
        text,
        count=1,
        flags=re.MULTILINE,
    )


def _fix_dict_license(text: str) -> str:
    """Replace `license = {text = "..."}` or `{file = "..."}` with SPDX."""
    return re.sub(
        r"^license\s*=\s*\{[^}]*\}",
        f'license = "{EXPECTED_LICENSE}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )


def _insert_classifier(text: str) -> str:
    """Insert the AGPL classifier into the classifiers array.

    If no `classifiers = [...]` block exists, create one right after the
    `license = "..."` line (keeps project metadata clustered).
    """
    if EXPECTED_CLASSIFIER in text:
        return text
    m = re.search(r"(classifiers\s*=\s*\[)(.*?)(\])", text, re.DOTALL)
    if m:
        body = m.group(2)
        insert = f'    "{EXPECTED_CLASSIFIER}",\n'
        new_mid = "\n" + insert + body.lstrip("\n")
        return text[: m.start()] + m.group(1) + new_mid + m.group(3) + text[m.end() :]
    # No classifiers array — create one immediately after the license line.
    lic_m = re.search(r'^(license\s*=\s*"[^"]+")\s*\n', text, re.MULTILINE)
    if not lic_m:
        return text
    block = f'classifiers = [\n    "{EXPECTED_CLASSIFIER}",\n]\n'
    return text[: lic_m.end()] + block + text[lic_m.end() :]


def plan_repo(repo: Path, reference_license: str) -> dict:
    """Return a dict describing what would be changed (no writes)."""
    actions: list[str] = []
    py = repo / "pyproject.toml"
    txt = py.read_text(encoding="utf-8")
    new_txt = txt

    m = re.search(r'^license\s*=\s*"([^"]+)"', new_txt, re.MULTILINE)
    if m and m.group(1) == "AGPL-3.0":
        new_txt = _fix_spdx(new_txt)
        actions.append('pyproject: "AGPL-3.0" → "AGPL-3.0-only"')
    elif re.search(r"^license\s*=\s*\{", new_txt, re.MULTILINE):
        new_txt = _fix_dict_license(new_txt)
        actions.append(f'pyproject: dict → "{EXPECTED_LICENSE}"')

    if EXPECTED_CLASSIFIER not in new_txt:
        new_txt2 = _insert_classifier(new_txt)
        if new_txt2 != new_txt:
            new_txt = new_txt2
            actions.append("pyproject: add AGPL classifier")
        else:
            actions.append(
                "pyproject: classifier missing AND could not find "
                "classifiers array (manual fix required)"
            )

    lf = repo / "LICENSE"
    need_license_copy = not lf.is_file()

    return {
        "repo": repo,
        "actions": actions,
        "pyproject_new": new_txt if new_txt != txt else None,
        "license_text": reference_license if need_license_copy else None,
    }


def apply_plan(plan: dict) -> list[Path]:
    """Write the plan to disk; returns list of modified paths."""
    changed: list[Path] = []
    if plan["pyproject_new"] is not None:
        (plan["repo"] / "pyproject.toml").write_text(
            plan["pyproject_new"], encoding="utf-8"
        )
        changed.append(plan["repo"] / "pyproject.toml")
    if plan["license_text"] is not None:
        (plan["repo"] / "LICENSE").write_text(plan["license_text"], encoding="utf-8")
        changed.append(plan["repo"] / "LICENSE")
    return changed


def commit_via_guard(repo: Path, files: list[Path], message: str) -> int:
    """Stage `files` then commit via git_guard_commit.sh for scope safety."""
    if not (repo / ".git").exists():
        print(f"  ! skipping commit — {repo} is not a git repo")
        return 2
    rel = [str(f.relative_to(repo)) for f in files]
    # Stage only the files we touched.
    add = subprocess.run(["git", "-C", str(repo), "add", "--", *rel], check=False)
    if add.returncode != 0:
        print(f"  ! git add failed (rc={add.returncode})")
        return add.returncode
    cmd = [
        str(GUARD_SCRIPT),
        "--repo",
        str(repo),
        *rel,
        "--",
        "-m",
        message,
    ]
    r = subprocess.run(cmd, check=False)
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects-root", type=Path, default=Path.home() / "proj")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes (default: dry-run)",
    )
    ap.add_argument(
        "--commit",
        action="store_true",
        help="Also commit each repo via git_guard_commit.sh (requires --apply)",
    )
    args = ap.parse_args()

    if args.commit and not args.apply:
        print("--commit requires --apply", file=sys.stderr)
        return 2

    reference = _canonical_license_text(args.projects_root)

    fixed = 0
    skipped_dirty: list[str] = []
    skipped_clean: list[str] = []

    for d in sorted(args.projects_root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if not in_scope(d):
            continue
        if not check_repo(d):
            continue  # already compliant

        if _is_dirty(d):
            skipped_dirty.append(d.name)
            print(f"[{d.name}] SKIP — dirty tree")
            continue

        plan = plan_repo(d, reference)
        if not plan["actions"] and plan["license_text"] is None:
            skipped_clean.append(d.name)
            continue

        print(f"[{d.name}]")
        for a in plan["actions"]:
            print(f"  + {a}")
        if plan["license_text"] is not None:
            print("  + LICENSE: copy AGPL v3 full text")

        if args.apply:
            changed = apply_plan(plan)
            fixed += 1
            if args.commit and changed:
                rc = commit_via_guard(
                    d,
                    changed,
                    "chore(license): normalize to AGPL-3.0-only "
                    "(SPDX form + classifier + LICENSE file)",
                )
                if rc != 0:
                    print(f"  ! commit failed (rc={rc})")

    print()
    if skipped_dirty:
        print(
            f"Skipped {len(skipped_dirty)} dirty tree(s) — apply manually:\n  "
            + "\n  ".join(skipped_dirty)
        )
    if not args.apply:
        print("\nDry-run complete. Re-run with --apply (and optionally --commit).")
    else:
        print(f"Applied to {fixed} repo(s).")
    return 0


if __name__ == "__main__":
    # Allow importing audit_license.py from the same directory when run
    # as a standalone script.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
