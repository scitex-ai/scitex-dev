#!/usr/bin/env python3
"""Ecosystem-wide quality audit — emits machine-readable JSON.

Detects regressions seen in the wild on 2026-04-28:
- missing `scitex-config` runtime dep when src/ imports it
- pyproject ↔ git tag ↔ PyPI version drift
- packages in registry but missing on disk (or vice versa)
- missing `_skills/<pkg>/SKILL.md`
- hardcoded `~/.cache/scitex/`, `~/.config/scitex/`, `/tmp/scitex-*`
- missing `.readthedocs.yaml`

Output: write JSON to `quality-audits/YYYY-MM-DD_ecosystem.json` (or
`--out`). Exit 1 if any HIGH/CRITICAL findings, 0 otherwise. Designed
to be run by a nightly workflow that commits the JSON back so the next
audit iteration sees yesterday's state.

Usage:
    python scripts/quality/audit_ecosystem.py
    python scripts/quality/audit_ecosystem.py --out /tmp/audit.json
    python scripts/quality/audit_ecosystem.py --projects-root ~/proj
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


@dataclass
class Finding:
    package: str
    section: str
    severity: str
    lens: str
    message: str
    detail: str = ""


@dataclass
class PackageReport:
    package: str
    on_disk: bool = False
    in_registry: bool = False
    pyproject_version: str | None = None
    latest_tag: str | None = None
    pypi_version: str | None = None
    findings: list[Finding] = field(default_factory=list)


def latest_semver_tag(repo: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "tag", "--list", "v*"], text=True
        )
    except subprocess.CalledProcessError:
        return None
    tags = [t.strip() for t in out.splitlines() if t.strip()]
    if not tags:
        return None

    def keyer(t: str) -> tuple:
        m = re.match(r"v(\d+)\.(\d+)\.(\d+)", t)
        if not m:
            return (0, 0, 0, t)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), t)

    return sorted(tags, key=keyer)[-1]


def pypi_version(name: str) -> str | None:
    try:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/json", timeout=10
        ) as fh:
            data = json.load(fh)
        return data["info"]["version"]
    except Exception:
        return None


def read_pyproject_version(pyproject: Path) -> str | None:
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


def read_pyproject_name(pyproject: Path) -> str | None:
    """Return [project].name verbatim, or None if missing/unreadable."""
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


def declares_dep(pyproject: Path, dep: str) -> bool:
    """Return True if `dep` appears in [project].dependencies (not optional).

    Uses tomllib so nested brackets in extras (e.g. `django-allauth[social]`)
    don't fool a regex that mistakes the inner ``]`` for the end of the deps
    list.
    """
    try:
        import tomllib  # py311+

        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return False
    deps = (data.get("project") or {}).get("dependencies") or []
    for d in deps:
        name = re.split(r"[\[<>=!~ ;]", d, maxsplit=1)[0].strip()
        if name == dep:
            return True
    return False


def import_name_for(package: str) -> str:
    return package.replace("-", "_")


def grep_uses_scitex_config(src: Path) -> bool:
    if not src.is_dir():
        return False
    try:
        out = subprocess.check_output(
            ["grep", "-rln", "from scitex_config\\|import scitex_config", str(src)],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return False
    # Filter __pycache__ and .pyc binary matches
    return any(
        line and "__pycache__" not in line and not line.endswith(".pyc")
        for line in out.splitlines()
    )


def grep_hardcodes(src: Path) -> list[str]:
    """Return file paths with hardcoded local-state paths (excluding docstrings/scripts)."""
    if not src.is_dir():
        return []
    try:
        out = subprocess.check_output(
            [
                "grep",
                "-rln",
                "-E",
                r"~/\.cache/scitex|~/\.config/scitex|/tmp/scitex",
                str(src),
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return []
    hits = []
    for line in out.splitlines():
        if not line:
            continue
        if "__pycache__" in line or line.endswith(".pyc"):
            continue
        if "/.claude/" in line or "/_skills/" in line:
            continue  # skill / claude-md docs, not active code
        if line.endswith(".sh") or line.endswith(".md"):
            continue  # scripts and docs
        # Skip generated sphinx output and pending JSON tool-use captures.
        if "/_sphinx_html/" in line or "/.pending/" in line:
            continue
        if line.endswith(".html") or line.endswith(".json") or line.endswith(".pickle"):
            continue
        if "/_sphinx" in line or "/.doctrees/" in line:
            continue
        hits.append(line)
    return hits


def audit_one(package: str, repo_root: Path, registry: dict[str, Any]) -> PackageReport:
    rep = PackageReport(package=package)
    rep.in_registry = package in registry
    rep.on_disk = repo_root.is_dir()
    if not rep.on_disk:
        if rep.in_registry:
            rep.findings.append(
                Finding(
                    package=package,
                    section="A2",
                    severity="MEDIUM",
                    lens="standardized",
                    message="registry references missing local path",
                    detail=f"{repo_root} (from registry) does not exist",
                )
            )
        return rep

    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        rep.findings.append(
            Finding(
                package=package,
                section="C1",
                severity="HIGH",
                lens="working",
                message="pyproject.toml missing",
                detail=str(pyproject),
            )
        )
        return rep

    rep.pyproject_version = read_pyproject_version(pyproject)
    rep.latest_tag = latest_semver_tag(repo_root)
    rep.pypi_version = pypi_version(package)

    # --- §A: registry consistency ---
    if not rep.in_registry:
        rep.findings.append(
            Finding(
                package=package,
                section="A2",
                severity="MEDIUM",
                lens="standardized",
                message="package on disk but absent from registry",
            )
        )

    # --- §C5+§C9+§C10+§C11: pyproject lint ---
    # Delegate to scitex_dev._pyproject_lint so the rules stay in one place
    # (it ships unit tests). Each rule maps to its checklist §-section.
    try:
        from scitex_dev._ecosystem._release.pyproject_lint import (
            lint_pyproject as _lint,
        )

        lint_rep = _lint(repo_root, package_name=package)
        for f in lint_rep.findings:
            section = {
                "REL-5_implicit_deps": "C5",
                "REL-9_skill_bundling": "C9",
                "REL-10_duplicate_table": "C10",
                "REL-11_invalid_pep639_license": "C11",
                "E5C1_missing_pyproject": "C1",
                "REL-21_dirty_release_state": "L2",
            }.get(f.rule, f.rule)
            rep.findings.append(
                Finding(
                    package=package,
                    section=section,
                    severity=f.severity,
                    lens="working",
                    message=f.message,
                    detail=f.detail,
                )
            )
    except Exception:
        # Fall back to the legacy single-rule check so the audit stays
        # functional even if the import fails (e.g. CI clones scitex-dev
        # at an older sha than the auditor expects).
        src = repo_root / "src" / import_name_for(package)
        if (
            package != "scitex-config"
            and grep_uses_scitex_config(src)
            and not declares_dep(pyproject, "scitex-config")
        ):
            rep.findings.append(
                Finding(
                    package=package,
                    section="C5",
                    severity="CRITICAL",
                    lens="working",
                    message="src imports scitex_config but pyproject does not declare scitex-config",
                    detail="fresh-venv install will fail at import",
                )
            )

    # --- §L2: pyproject / tag / pypi alignment ---
    if rep.pyproject_version and rep.pypi_version:
        if rep.pyproject_version != rep.pypi_version:
            rep.findings.append(
                Finding(
                    package=package,
                    section="L2",
                    severity="LOW",
                    lens="trustful",
                    message="pyproject differs from PyPI",
                    detail=f"pyproject={rep.pyproject_version} pypi={rep.pypi_version}",
                )
            )
    if rep.latest_tag and rep.pyproject_version:
        if rep.latest_tag.lstrip("v") != rep.pyproject_version:
            rep.findings.append(
                Finding(
                    package=package,
                    section="L2",
                    severity="LOW",
                    lens="trustful",
                    message="latest tag differs from pyproject",
                    detail=f"tag={rep.latest_tag} pyproject={rep.pyproject_version}",
                )
            )

    # --- §E: skills bundling ---
    src = repo_root / "src" / import_name_for(package)
    skill_md = src / "_skills" / package / "SKILL.md"
    if not skill_md.is_file():
        rep.findings.append(
            Finding(
                package=package,
                section="E1",
                severity="MEDIUM",
                lens="useful",
                message="missing _skills/<pkg>/SKILL.md",
                detail=str(skill_md),
            )
        )

    # --- §D1: hardcoded local-state paths ---
    hits = grep_hardcodes(src)
    if hits:
        rep.findings.append(
            Finding(
                package=package,
                section="D1",
                severity="MEDIUM",
                lens="standardized",
                message=f"{len(hits)} hardcoded local-state path(s) in src/",
                detail="; ".join(h.split("/scitex-")[-1] for h in hits[:5]),
            )
        )

    # --- §J4: RTD config ---
    rtd_yaml = repo_root / ".readthedocs.yaml"
    if not rtd_yaml.is_file():
        rep.findings.append(
            Finding(
                package=package,
                section="J4",
                severity="LOW",
                lens="useful",
                message="missing .readthedocs.yaml (RTD not wired)",
            )
        )

    return rep


def load_registry(repo_root: Path) -> dict[str, dict[str, str]]:
    """Load `scitex_dev.ecosystem.ECOSYSTEM` without importing scitex-dev.

    Returns a name -> {local_path, ...} mapping. Local path is parsed so the
    auditor can resolve packages whose dirname differs from the registry key
    (e.g. `scitex` lives at `~/proj/scitex-python/`).
    """
    # Layout fallback chain (newest layout first):
    #   1. 0.17.0+ — `_ecosystem/_registry.py` owns the ECOSYSTEM dict
    #      literal; `_core.py` only does `from ._registry import ECOSYSTEM`
    #      and so has no dict literals for the regex below to match.
    #      (0.17.7 release exposed this: the script silently returned
    #      an empty registry → downstream audit crashed with the
    #      operator-visible FileNotFoundError on the ecosystem registry
    #      file — see 0.17.8 CHANGELOG.)
    #   2. 0.11.0 – 0.16.x — `_ecosystem/_core.py` owned the dict inline.
    #   3. pre-0.11.0 — flat `scitex_dev/ecosystem.py` owned the dict
    #      inline. Kept so the same script can audit older repos / tags.
    candidates = [
        repo_root / "src" / "scitex_dev" / "_ecosystem" / "_registry.py",
        repo_root / "src" / "scitex_dev" / "_ecosystem" / "_core.py",
        repo_root / "src" / "scitex_dev" / "ecosystem.py",
    ]
    eco_py = next((p for p in candidates if p.is_file()), None)
    if eco_py is None:
        return {}
    text = eco_py.read_text(encoding="utf-8")
    out: dict[str, dict[str, str]] = {}
    # Match `"<key>": { ...inner... }` per entry.  Allow newline between key
    # and opening brace (new _registry.py layout: multiline entries).
    for m in re.finditer(
        r'^\s*"([\w-]+)"\s*:\s*\n?\s*(.*?)\n\s*\}',
        text,
        re.MULTILINE | re.DOTALL,
    ):
        name = m.group(1)
        body = m.group(2)
        info: dict[str, str] = {}
        for k in ("local_path", "pypi_name", "github_repo", "import_name", "category"):
            mm = re.search(rf'"{k}"\s*:\s*"([^"]+)"', body)
            if mm:
                info[k] = mm.group(1)
        info.setdefault("category", "library")
        out[name] = info
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects-root", default=str(Path.home() / "proj"))
    parser.add_argument(
        "--scitex-dev-root",
        default=None,
        help="Path to scitex-dev repo (registry source); default = projects-root/scitex-dev",
    )
    parser.add_argument("--out", default=None)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--categories",
        default="umbrella,library,external-lib",
        help="Comma-separated category list to audit "
        "(default skips templates and datasets). Pass 'all' to include every category.",
    )
    args = parser.parse_args()
    selected_categories = (
        None if args.categories == "all" else set(args.categories.split(","))
    )

    projects_root = Path(args.projects_root).expanduser()
    scitex_dev_root = (
        Path(args.scitex_dev_root).expanduser()
        if args.scitex_dev_root
        else projects_root / "scitex-dev"
    )

    registry = load_registry(scitex_dev_root)

    # Discover on-disk packages with the periodic-checklist scope gate
    # (`pyproject.name == basename`). Skip symlinks (e.g. legacy
    # scitex-tunnel→scitex-ssh shim), `*bak*` archives, and dirs whose
    # pyproject identifies a different package. This filters out paper repos
    # (scitex-paper-1st), the umbrella source dir (scitex-python whose
    # pyproject.name is "scitex"), and rename leftovers without listing each
    # one explicitly.
    on_disk: set[str] = set()
    for p in projects_root.iterdir():
        if not p.is_dir() or p.is_symlink():
            continue
        name = p.name
        if not (name.startswith("scitex-") or name == "scitex"):
            continue
        if "bak" in name or name.endswith("-old"):
            continue
        pyproject = p / "pyproject.toml"
        if not pyproject.is_file():
            continue
        declared = read_pyproject_name(pyproject)
        if declared and declared != name:
            continue
        on_disk.add(name)

    candidates = sorted(set(registry) | on_disk)

    reports: list[PackageReport] = []
    for pkg in candidates:
        info = registry.get(pkg) or {}
        category = info.get("category", "library")
        if selected_categories is not None and category not in selected_categories:
            continue
        local_path = info.get("local_path") or f"~/proj/{pkg}"
        repo = Path(local_path).expanduser()
        if not repo.is_dir():
            # Fall back to projects_root/<key> for unregistered on-disk hits.
            repo = projects_root / pkg
        rep = audit_one(pkg, repo, registry)
        reports.append(rep)

    # Aggregate
    total_findings = sum(len(r.findings) for r in reports)
    by_severity = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in reports:
        for f in r.findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projects_root": str(projects_root),
        "summary": {
            "packages_audited": len(reports),
            "total_findings": total_findings,
            "by_severity": by_severity,
        },
        "packages": [
            {
                **asdict(r),
                "findings": [asdict(f) for f in r.findings],
            }
            for r in reports
        ],
    }

    if args.out:
        out = Path(args.out).expanduser()
    else:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out = scitex_dev_root / "quality-audits" / f"{date}_ecosystem.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")

    if not args.quiet:
        print(f"Wrote {out}")
        print(f"  packages: {len(reports)}")
        print(f"  findings: {total_findings}")
        print(f"  by severity: {by_severity}")

    return 1 if (by_severity.get("CRITICAL", 0) + by_severity.get("HIGH", 0)) else 0


if __name__ == "__main__":
    sys.exit(main())
