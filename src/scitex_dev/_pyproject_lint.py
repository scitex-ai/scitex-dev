#!/usr/bin/env python3
# Timestamp: 2026-04-28
# File: scitex_dev/_pyproject_lint.py

"""Lint a pyproject.toml against ecosystem invariants.

Codifies the regressions caught during the 2026-04-28 audit pass so an
agent doesn't have to rediscover them by re-running the full audit
script every time. Each rule has a stable id (`E5C5`, `E5C9`, …) keyed
to the §-numbers in `general/99_quality_02_checklist.md` so findings
join the same triage flow.

Rules
-----
- ``E5C5_implicit_deps`` — every ecosystem package imported anywhere
  under ``src/<pkg>/`` must appear in
  ``[project].dependencies``. Caught the 2026-04-28 class-action where
  6 packages broke on PyPI by importing ``scitex_config._ecosystem``
  without declaring ``scitex-config``.
- ``E5C9_skill_bundling`` — if ``src/<pkg>/_skills/`` exists, the build
  must (a) include ``_skills/**/*.md`` in package-data and (b) register
  the ``scitex_dev.skills`` entry-point. Caught packages whose SKILL.md
  was on disk but never shipped on PyPI.
- ``E5C10_duplicate_table`` — TOML 1.0 forbids declaring the same
  table twice; setuptools is silent about it but tomllib raises. Caught
  scitex-resource and scitex-capture this session.
- ``E5C11_invalid_pep639_license`` — `license = "AGPL-3.0-only"` is the
  ecosystem standard. Caught packages still using
  `license = {text = "..."}` (deprecated PEP 621 form).
- ``E5L1_dirty_release_state`` — pyproject version, latest git tag, and
  PyPI latest must agree (within drift tolerance). Caught the
  scitex-stats / scitex-cloud / scitex-orochi tag-vs-PyPI drift.

Each check returns a list of ``LintFinding`` records. The CLI maps them
to ``scitex-dev quality lint-pyproject [--fix] [--strict]``.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Map import_name → pip name. Used by E5C5 to recognise an import as
# "this is an ecosystem package".
ECOSYSTEM_IMPORTS_TO_DIST: dict[str, str] = {
    "scitex_config": "scitex-config",
    "scitex_core": "scitex-core",
    "scitex_io": "scitex-io",
    "scitex_dev": "scitex-dev",
    "scitex_logging": "scitex-logging",
    "scitex_path": "scitex-path",
    "scitex_types": "scitex-types",
    "scitex_str": "scitex-str",
    "scitex_dict": "scitex-dict",
    "scitex_dt": "scitex-datetime",
    "scitex_datetime": "scitex-datetime",
    "scitex_decorators": "scitex-decorators",
    "scitex_repro": "scitex-repro",
    "scitex_compat": "scitex-compat",
    "scitex_session": "scitex-session",
    "scitex_context": "scitex-context",
    "scitex_os": "scitex-os",
    "scitex_sh": "scitex-sh",
    "scitex_git": "scitex-git",
    "scitex_introspect": "scitex-introspect",
    "scitex_stats": "scitex-stats",
    "scitex_pd": "scitex-pd",
    "scitex_dsp": "scitex-dsp",
    "scitex_nn": "scitex-nn",
    "scitex_linalg": "scitex-linalg",
    "scitex_cv": "scitex-cv",
    "scitex_audio": "scitex-audio",
    "scitex_capture": "scitex-capture",
    "scitex_db": "scitex-db",
    "scitex_dataset": "scitex-dataset",
    "scitex_scholar": "scitex-scholar",
    "scitex_writer": "scitex-writer",
    "scitex_msword": "scitex-msword",
    "scitex_tex": "scitex-tex",
    "scitex_web": "scitex-web",
    "scitex_security": "scitex-security",
    "scitex_resource": "scitex-resource",
    "scitex_orochi": "scitex-orochi",
    "scitex_events": "scitex-events",
    "scitex_hpc": "scitex-hpc",
    "scitex_clew": "scitex-clew",
    "scitex_cloud": "scitex-cloud",
    "scitex_browser": "scitex-browser",
    "scitex_app": "scitex-app",
    "scitex_ui": "scitex-ui",
    "scitex_container": "scitex-container",
    "scitex_ssh": "scitex-ssh",
    "scitex_agent_container": "scitex-agent-container",
    "scitex_template": "scitex-template",
    "scitex_skills": "scitex-skills",
    "scitex_audit": "scitex-audit",
    "scitex_etc": "scitex-etc",
    "scitex_gists": "scitex-gists",
    "scitex_parallel": "scitex-parallel",
    "scitex_plt": "scitex-plt",
    "scitex_gen": "scitex-gen",
    "scitex_notification": "scitex-notification",
    "scitex_benchmark": "scitex-benchmark",
    "scitex_bridge": "scitex-bridge",
    "scitex_linter": "scitex-linter",
    "figrecipe": "figrecipe",
    "socialia": "socialia",
}


@dataclass
class LintFinding:
    rule: str
    severity: str  # CRITICAL / HIGH / MEDIUM / LOW
    message: str
    detail: str = ""
    fix_hint: str = ""

    def render(self) -> str:
        out = f"[{self.severity:8s}] {self.rule}: {self.message}"
        if self.detail:
            out += f"\n    {self.detail}"
        if self.fix_hint:
            out += f"\n    fix: {self.fix_hint}"
        return out


@dataclass
class LintReport:
    package: str
    pyproject: Path
    findings: list[LintFinding] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "CRITICAL" for f in self.findings)

    @property
    def has_high(self) -> bool:
        return any(f.severity in ("CRITICAL", "HIGH") for f in self.findings)


def _load_pyproject(path: Path) -> dict[str, Any] | None:
    """Parse pyproject.toml; return None on parse error (caller flags it)."""
    try:
        import tomllib

        with path.open("rb") as fh:
            return tomllib.load(fh)
    except Exception:
        return None


def _src_dir(repo: Path, import_name: str) -> Path:
    return repo / "src" / import_name


def _scan_imports(src_dir: Path) -> set[str]:
    """Top-level module names UNCONDITIONALLY imported under src_dir.

    AST-based so we can distinguish optional imports (wrapped in
    ``try: import x; except ImportError``) from hard ones. Optional
    imports legitimately don't require a declared dep — they fall back
    to a stub when the package is missing — and the lint must NOT flag
    them. Hard imports (anywhere outside a try-block, including inside
    function bodies) are flagged.

    Returns the set of *top-level module roots* (e.g. `scitex_config`,
    not `scitex_config._ecosystem`). False negatives via
    ``importlib.import_module(...)`` are accepted; document in the rule.
    """
    import ast

    if not src_dir.is_dir():
        return set()

    out: set[str] = set()
    for py in src_dir.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError:
            continue

        class V(ast.NodeVisitor):
            def __init__(self):
                self.in_try_depth = 0

            def visit_Try(self, node: ast.Try):  # noqa: N802
                # Only the body of a try-block counts as guarded; the
                # except/finally blocks shouldn't grant immunity to
                # imports written there (rare but real).
                self.in_try_depth += 1
                for stmt in node.body:
                    self.visit(stmt)
                self.in_try_depth -= 1
                for handler in node.handlers:
                    for stmt in handler.body:
                        self.visit(stmt)
                for stmt in node.orelse:
                    self.visit(stmt)
                for stmt in node.finalbody:
                    self.visit(stmt)

            def _add(self, name: str | None):
                if name and self.in_try_depth == 0:
                    out.add(name.split(".")[0])

            def visit_Import(self, node: ast.Import):  # noqa: N802
                for alias in node.names:
                    self._add(alias.name)
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom):  # noqa: N802
                if node.module:
                    self._add(node.module)
                self.generic_visit(node)

        V().visit(tree)
    return out


def _declared_runtime_deps(data: dict[str, Any]) -> set[str]:
    raw = (data.get("project") or {}).get("dependencies") or []
    result = set()
    for d in raw:
        name = re.split(r"[\[<>=!~ ;]", d, maxsplit=1)[0].strip()
        if name:
            result.add(name)
    return result


def check_implicit_deps(
    repo: Path, pyproject_data: dict[str, Any], package_name: str
) -> list[LintFinding]:
    """Rule E5C5 — codifies the 2026-04-28 class-action."""
    findings: list[LintFinding] = []
    import_name = package_name.replace("-", "_")
    imports = _scan_imports(_src_dir(repo, import_name))
    declared = _declared_runtime_deps(pyproject_data)
    for mod in sorted(imports):
        dist = ECOSYSTEM_IMPORTS_TO_DIST.get(mod)
        if not dist or dist == package_name:
            continue
        if dist in declared:
            continue
        findings.append(
            LintFinding(
                rule="E5C5_implicit_deps",
                severity="CRITICAL",
                message=f"src imports `{mod}` but pyproject does not declare `{dist}`",
                detail="fresh-venv install will fail at import time with ModuleNotFoundError",
                fix_hint=f'add `"{dist}>=<min>"` to [project].dependencies',
            )
        )
    return findings


def _has_entry_point(data: dict[str, Any], group: str, key: str) -> bool:
    eps = (data.get("project") or {}).get("entry-points") or {}
    return key in (eps.get(group) or {})


def _skill_bundled(data: dict[str, Any], import_name: str) -> bool:
    """True iff the build will ship ``_skills/**/*.md`` for this import name.

    Backend-aware:

    - **setuptools** (``setuptools.build_meta``) needs explicit
      ``[tool.setuptools.package-data]`` because ``packages.find`` only
      keeps Python files. No glob → not bundled.
    - **hatchling** ships every file inside the package directory by
      default. We only flag when an explicit ``exclude`` drops
      ``_skills/`` or when an explicit ``include`` list omits it.
    - **unknown backend**: be conservative; assume bundled (avoid false
      positives — we'd rather miss a real bug than warn on every
      package).
    """
    tool = data.get("tool") or {}
    build_backend = (data.get("build-system") or {}).get("build-backend", "")

    if "setuptools" in build_backend:
        pkg_data = (tool.get("setuptools") or {}).get("package-data") or {}
        globs = pkg_data.get(import_name) or pkg_data.get("*") or []
        return any("_skills" in g for g in globs)

    if "hatch" in build_backend:
        wheel = (
            ((tool.get("hatch") or {}).get("build") or {}).get("targets") or {}
        ).get("wheel") or {}
        if any("_skills" in pat for pat in (wheel.get("exclude") or [])):
            return False
        if any("_skills" in src for src in (wheel.get("force-include") or {})):
            return True
        includes = wheel.get("include")
        if includes is not None:
            return any("_skills" in inc for inc in includes)
        # Default hatchling: everything in the package dir is shipped.
        return True

    # Unknown backend — don't make noise.
    return True


def check_skill_bundling(
    repo: Path, pyproject_data: dict[str, Any], package_name: str
) -> list[LintFinding]:
    """Rule E5C9 — _skills/ on disk implies bundling + entry-point."""
    findings: list[LintFinding] = []
    import_name = package_name.replace("-", "_")
    skills_dir = _src_dir(repo, import_name) / "_skills"
    if not skills_dir.is_dir():
        return findings
    if not _skill_bundled(pyproject_data, import_name):
        findings.append(
            LintFinding(
                rule="E5C9_skill_bundling",
                severity="HIGH",
                message="_skills/ on disk but package-data does not ship `_skills/**/*.md`",
                detail=f"PyPI users won't see {skills_dir.name}/<pkg>/SKILL.md",
                fix_hint=f'[tool.setuptools.package-data]\n    {import_name} = ["_skills/**/*.md"]',
            )
        )
    if not _has_entry_point(pyproject_data, "scitex_dev.skills", package_name):
        findings.append(
            LintFinding(
                rule="E5C9_skill_bundling",
                severity="HIGH",
                message="_skills/ on disk but no `scitex_dev.skills` entry-point",
                detail="agents won't discover the package via importlib.metadata",
                fix_hint=f'[project.entry-points."scitex_dev.skills"]\n    {package_name} = "{import_name}"',
            )
        )
    return findings


_DUP_TABLE_RE = re.compile(r"^\s*\[(?:tool|project)[\w.\-]*\]", re.MULTILINE)


def check_duplicate_tables(pyproject: Path) -> list[LintFinding]:
    """Rule E5C10 — surface 'cannot declare twice' errors before they bite."""
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return []
    seen: dict[str, int] = {}
    findings: list[LintFinding] = []
    for m in _DUP_TABLE_RE.finditer(text):
        header = m.group(0).strip()
        seen[header] = seen.get(header, 0) + 1
    for header, count in seen.items():
        if count > 1:
            findings.append(
                LintFinding(
                    rule="E5C10_duplicate_table",
                    severity="HIGH",
                    message=f"TOML table declared {count}× — {header}",
                    detail="setuptools accepts only the LAST declaration; tomllib refuses outright",
                    fix_hint="merge keys into a single table",
                )
            )
    return findings


def check_license(pyproject_data: dict[str, Any]) -> list[LintFinding]:
    """Rule E5C11 — AGPL-3.0-only as PEP 639 SPDX expression."""
    proj = pyproject_data.get("project") or {}
    lic = proj.get("license")
    if isinstance(lic, str):
        if lic.strip() == "AGPL-3.0-only":
            return []
        return [
            LintFinding(
                rule="E5C11_invalid_pep639_license",
                severity="MEDIUM",
                message=f"license is `{lic!r}`, expected SPDX `AGPL-3.0-only`",
                fix_hint='license = "AGPL-3.0-only"',
            )
        ]
    if isinstance(lic, dict):
        return [
            LintFinding(
                rule="E5C11_invalid_pep639_license",
                severity="MEDIUM",
                message="license uses deprecated table form (PEP 621 pre-639)",
                detail=f"got {lic!r}",
                fix_hint='license = "AGPL-3.0-only"   # PEP 639 SPDX expression',
            )
        ]
    return [
        LintFinding(
            rule="E5C11_invalid_pep639_license",
            severity="LOW",
            message="no license field in [project]",
            fix_hint='license = "AGPL-3.0-only"',
        )
    ]


def _pypi_version(name: str) -> str | None:
    try:
        import urllib.request
        import json

        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/json", timeout=10
        ) as fh:
            data = json.load(fh)
        return data["info"]["version"]
    except Exception:
        return None


def _latest_tag(repo: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "tag", "--list", "v*"],
            text=True,
            stderr=subprocess.DEVNULL,
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


def check_release_alignment(
    repo: Path, pyproject_data: dict[str, Any], package_name: str
) -> list[LintFinding]:
    """Rule E5L1 — pyproject ↔ tag ↔ PyPI alignment."""
    findings: list[LintFinding] = []
    py_ver = (pyproject_data.get("project") or {}).get("version")
    if not py_ver:
        return findings
    tag = _latest_tag(repo)
    pypi = _pypi_version(package_name)
    if tag and tag.lstrip("v") != py_ver:
        findings.append(
            LintFinding(
                rule="E5L1_dirty_release_state",
                severity="LOW",
                message=f"latest git tag `{tag}` ≠ pyproject version `{py_ver}`",
                fix_hint=f"git tag v{py_ver} && git push --tags",
            )
        )
    if pypi and pypi != py_ver:
        findings.append(
            LintFinding(
                rule="E5L1_dirty_release_state",
                severity="LOW",
                message=f"PyPI latest `{pypi}` ≠ pyproject version `{py_ver}`",
                detail="release in flight, or release stale",
            )
        )
    return findings


def lint_pyproject(repo: Path, package_name: str | None = None) -> LintReport:
    """Run every rule against `repo/pyproject.toml`. Used by CLI + tests."""
    pyproject = repo / "pyproject.toml"
    rep = LintReport(package=package_name or repo.name, pyproject=pyproject)
    if not pyproject.is_file():
        rep.findings.append(
            LintFinding(
                rule="E5C1_missing_pyproject",
                severity="HIGH",
                message="pyproject.toml not found at repo root",
            )
        )
        return rep
    rep.findings.extend(check_duplicate_tables(pyproject))
    data = _load_pyproject(pyproject)
    if data is None:
        rep.findings.append(
            LintFinding(
                rule="E5C10_duplicate_table",
                severity="HIGH",
                message="pyproject.toml fails to parse with tomllib",
                detail="usually a duplicate table; see E5C10 finding above for the offender",
            )
        )
        return rep
    pkg = package_name or (data.get("project") or {}).get("name")
    rep.package = pkg or repo.name
    rep.findings.extend(check_implicit_deps(repo, data, rep.package))
    rep.findings.extend(check_skill_bundling(repo, data, rep.package))
    rep.findings.extend(check_license(data))
    rep.findings.extend(check_release_alignment(repo, data, rep.package))
    return rep


__all__ = [
    "ECOSYSTEM_IMPORTS_TO_DIST",
    "LintFinding",
    "LintReport",
    "lint_pyproject",
    "check_implicit_deps",
    "check_skill_bundling",
    "check_duplicate_tables",
    "check_license",
    "check_release_alignment",
]
