"""PS-185 — gate-covers-CI drift detection.

Card: ``gate-covers-ci-lightweight`` (filed 2026-06-15). The pre-push
gate exists to cover CI's LIGHTWEIGHT, diff-scopable checks locally so
the operator does not push → red → patch → push → red merry-go-round.
When CI adds a NEW lightweight job (a ruff variant, a new lint, a new
import-smoke) and the gate is not updated to match, the operator
loses ALL the local feedback for that new check until they next hit
red in CI. PS-185 catches that drift.

Invariant
---------
Every lightweight CI job listed in ``.github/workflows/*.yml`` SHOULD
have a corresponding step in the canonical pre-push gate script
(``src/scitex_dev/_hooks/pre-push.sh``). The rule operates on the
PRESENCE of the job-class keyword in the gate script — exact wording
is intentionally fuzzy because the gate is a shell script, not a
structured config.

Heavy CI items are EXEMPT — pytest-matrix, sphinx-docs, codecov upload,
the ecosystem-wide audit-all whole-repo run. The gate's purpose is the
lightweight subset; the matrix is CI-only by design.

The rule reads:

  * Every ``.github/workflows/*.yml`` file's top-level ``name:`` field
    AND every ``jobs.<id>.name:`` field, lower-cased.
  * Compares each name against a LIGHTWEIGHT_KEYWORDS map. A hit means
    the job is in scope.
  * Looks up each in-scope keyword in the gate script's text. If the
    keyword appears in the gate (anywhere in the file), it's covered.
  * Each in-scope keyword NOT covered by the gate yields a PS-185
    violation, citing the workflow file + the gate path.

Exemption mechanisms:

  1. **HEAVY_EXEMPT** literal list inside this module (the canonical
     exempt set: pytest-matrix, sphinx, codecov, ecosystem-audit).
  2. Workflow file-level comment marker ``# PS-185-exempt: <reason>``
     anywhere in the YAML file's first 40 lines — opts the whole file
     out (used for one-offs that don't fit the literal exempt list).

The rule fires on the scitex-dev repo itself; PS-185 is a development
discipline rule (severity W during adoption — promote to E once the
gate has stabilised across the ecosystem).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Job-class keywords the gate is expected to cover.
#
# Keys are lower-case substrings to look for in workflow `name:` fields;
# values are tuples of substrings the gate script MUST contain for the
# check to count as covered. Multiple alternatives are OR'd (any one is
# enough).
# ---------------------------------------------------------------------------
LIGHTWEIGHT_KEYWORDS: dict[str, tuple[str, ...]] = {
    # ruff or any "lint" job — the gate's `ruff check --select` line
    # satisfies both.
    "ruff": ("ruff check", "ruff "),
    "lint": ("ruff check", "ruff ", "run_lint"),
    # import-smoke / install-check — the gate's `import-smoke` step
    # under the `[3/4]` echo satisfies these.
    "import-smoke": ("import-smoke", "importlib.import_module"),
    "install-check": ("import-smoke", "importlib.import_module"),
    # audit — the gate's audit-all step covers this.
    "audit": ("audit-all", "ecosystem audit"),
    "quality": ("audit-all", "ecosystem audit"),
}

# Heavy CI items — exempt from the gate-coverage check by design.
# Names matched case-insensitive as substrings against workflow `name:`
# fields AND filename stems.
HEAVY_EXEMPT: frozenset[str] = frozenset(
    {
        "tests",  # pytest-matrix top-level job name
        "pytest-matrix",
        "pytest",
        "rtd-sphinx",
        "sphinx",
        "docs",
        "codecov",
        "auto-merge",
        "cla",
        "pypi-publish",
        "release",
        "sync-main",
        "sdk-runtime-smoke",
        "cli-smoke",
        "newb-docs-quality",
    }
)

# Per-file opt-out marker — any workflow YAML whose first 40 lines
# contain this comment is excluded wholesale.
_FILE_OPTOUT_RE = re.compile(r"#\s*PS-185-exempt\b", re.IGNORECASE)

# Match the first `name:` line (workflow-level), case-insensitive,
# tolerant of indentation. We also capture every `name:` inside `jobs:`
# blocks for jobs that override the workflow-level name.
_NAME_RE = re.compile(r"^\s*name\s*:\s*(.+?)\s*$", re.MULTILINE)


def _read_workflow_names(yml_path: Path) -> list[str]:
    """Return every `name:` value in the workflow file (lower-cased).

    Strips surrounding quotes. Returns an empty list if the file is
    missing, unreadable, or opts out via ``# PS-185-exempt``.
    """
    try:
        text = yml_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    head = "\n".join(text.splitlines()[:40])
    if _FILE_OPTOUT_RE.search(head):
        return []
    out: list[str] = []
    for m in _NAME_RE.finditer(text):
        raw = m.group(1).strip().strip("\"'")
        if raw:
            out.append(raw.lower())
    return out


def _is_heavy_exempt(name: str, filename_stem: str) -> bool:
    """Return True iff the workflow is in the heavy-exempt set."""
    lower_stem = filename_stem.lower()
    for keyword in HEAVY_EXEMPT:
        if keyword in name or keyword in lower_stem:
            return True
    return False


def _gate_script_text(repo: Path) -> str | None:
    """Return the canonical pre-push gate's text, or None if absent.

    Probes the bundled script's location inside scitex-dev FIRST (the
    canonical source of truth), then falls back to the symlinked
    ``.githooks/pre-push`` in the target repo. Either is acceptable —
    when both exist they SHOULD be the same file (the symlink points at
    the bundled script).
    """
    # 1. Canonical bundled path (when we're auditing scitex-dev itself).
    bundled = repo / "src" / "scitex_dev" / "_hooks" / "pre-push.sh"
    if bundled.is_file():
        try:
            return bundled.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    # 2. Symlinked .githooks/pre-push in the target repo.
    deployed = repo / ".githooks" / "pre-push"
    if deployed.is_file() or deployed.is_symlink():
        try:
            return deployed.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    # 3. Pre-installed via the scitex-dev wheel (resolve the package
    # path at runtime so this works in editable installs too).
    try:
        from scitex_dev._hooks import pre_push_sh_path

        path = Path(pre_push_sh_path())
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    except (ImportError, OSError):
        pass
    return None


def check_ps185_gate_coverage(repo: Path, violation_cls: type, out: list[Any]) -> None:
    """PS-185 — every lightweight CI job is covered by the pre-push gate.

    Reads ``.github/workflows/*.yml`` and compares against the canonical
    pre-push gate script. Each lightweight CI job (ruff / import-smoke /
    audit) whose keyword does NOT appear in the gate yields one
    violation citing both the workflow file and the gate path. Heavy
    items (pytest-matrix, sphinx, codecov) are exempt by design.
    """
    workflows_dir = repo / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return

    gate_text = _gate_script_text(repo)
    if gate_text is None:
        # No gate to compare against — the rule degrades silently.
        # A separate rule (PS-101-class) catches the missing gate.
        return
    gate_lower = gate_text.lower()

    for yml_path in sorted(workflows_dir.iterdir()):
        if yml_path.suffix not in {".yml", ".yaml"} or not yml_path.is_file():
            continue
        names = _read_workflow_names(yml_path)
        if not names:
            continue
        # If ANY name in the file is heavy-exempt, the whole file is
        # exempt — workflow-level names usually identify the file's
        # purpose, and jobs share that scope.
        if any(_is_heavy_exempt(n, yml_path.stem) for n in names):
            continue
        # Otherwise: every name that matches a lightweight keyword
        # must be covered.
        for name in names:
            for keyword, gate_signatures in LIGHTWEIGHT_KEYWORDS.items():
                if keyword not in name:
                    continue
                covered = any(sig.lower() in gate_lower for sig in gate_signatures)
                if covered:
                    continue
                out.append(
                    violation_cls(
                        "PS-185",
                        str(yml_path),
                        (
                            f"workflow '{name}' has a lightweight "
                            f"`{keyword}` check that the pre-push gate "
                            f"does NOT mirror. Add a corresponding step "
                            f"to `src/scitex_dev/_hooks/pre-push.sh` so "
                            f"the operator catches the same red locally "
                            f"before push. Heavy items (pytest-matrix, "
                            f"sphinx, codecov) stay CI-only; the gate is "
                            f"the LIGHTWEIGHT subset. Opt-out: add "
                            f"`# PS-185-exempt: <reason>` to the "
                            f"workflow's first 40 lines."
                        ),
                    )
                )
                # Only one finding per (file, keyword) pair — break to
                # the next keyword once we've flagged this one.
                break
