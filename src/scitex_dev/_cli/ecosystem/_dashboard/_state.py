"""Data layer for the ecosystem dashboard.

`gather_ecosystem_state(verbosity)` returns a list of `PackageState`,
one per ECOSYSTEM entry. Higher verbosity adds slower / networked
columns:

  -v   (1, default) PKG, CAT, VER, TAG, AHEAD, BRANCH, SKIP, AUDIT_E,
                    AUDIT_W, DRIFT_LOCAL
  -vv  (2)          + PYPI, DRIFT_PYPI, CI
  -vvv (3)          + RTD, SKILLS, MCP_TOOLS, PY_APIS, TESTS, COV, LOC,
                    SKIP_RULES_LIST

Verbosity 0 collapses to PKG, AUDIT_E, DRIFT_LOCAL, CI for the at-a-
glance "what's red?" view.

All filesystem + git lookups are local-fast (~1ms each, parallel).
PyPI / RTD / GH Actions are deferred behind `verbosity >= 2`; results
are cached on the returned record so the renderer can show partial
rows immediately and fill the rest as fetches complete.
"""

from __future__ import annotations

import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_PROJ_ROOT = Path("~/proj").expanduser()


@dataclass
class PackageState:
    pkg: str
    category: str = ""
    local_path: str = ""
    exists_locally: bool = False

    # Versions
    version_pyproject: str = ""
    version_dynamic: bool = False  # uses setuptools-scm
    tag_latest: str = ""
    pypi_latest: str = ""

    # Drift summary (computed)
    drift_local: str = ""  # ✓ / V≠T / V<T / V>T
    drift_pypi: str = ""  # ✓ / T>P / T<P

    # Git
    branch: str = ""
    ahead: int = 0
    last_commit_iso: str = ""

    # Audit gate
    has_audit_gate: bool = False
    skip_rules: list[str] = field(default_factory=list)
    audit_errors: int = -1  # -1 = not run
    audit_warnings: int = -1

    # CI
    ci_status: str = ""  # success / failure / in_progress / cancelled / ""

    # Deep (verbosity >= 3)
    rtd_status: str = ""
    skills_count: int = -1
    mcp_tools: int = -1
    py_apis: int = -1
    tests_count: int = -1
    coverage: float = -1.0
    loc: int = -1

    def to_dict(self) -> dict:
        return asdict(self)


def _git(repo: Path, *args: str, default: str = "") -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), *args],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip()
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return default


def _read_pyproject_version(repo: Path) -> tuple[str, bool]:
    """Return (version_str, is_dynamic). Empty string if not found."""
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return "", False
    try:
        text = pp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", False
    # Static version
    m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if m:
        return m.group(1), False
    # Dynamic
    if re.search(r'^\s*dynamic\s*=\s*\[[^\]]*"version"', text, re.MULTILINE):
        return "(dynamic)", True
    return "", False


def _read_skip_rules(repo: Path) -> list[str]:
    """Extract the skip_rules tuple from tests/develop/test_audit.py.

    Source-of-truth scan, not import-and-call: the audit gate file is
    code we generate, so the literal pattern is stable.
    """
    f = repo / "tests" / "develop" / "test_audit.py"
    if not f.is_file():
        return []
    try:
        src = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    block = re.search(r"skip_rules\s*=\s*\(([^)]*)\)", src, re.DOTALL)
    if not block:
        return []
    return re.findall(r'"([^"]+)"', block.group(1))


def _has_audit_gate(repo: Path) -> bool:
    return (repo / "tests" / "develop" / "test_audit.py").is_file()


def _latest_tag(repo: Path) -> str:
    """Most recent vX.Y.Z tag (lexical fallback if no semver)."""
    tag = _git(repo, "describe", "--tags", "--abbrev=0", "--match", "v*")
    return tag


def _branch(repo: Path) -> str:
    return _git(repo, "branch", "--show-current")


def _ahead_of_origin(repo: Path) -> int:
    """How many commits HEAD is ahead of origin/<current_branch>."""
    br = _branch(repo)
    if not br:
        return 0
    out = _git(repo, "rev-list", "--count", f"origin/{br}..HEAD")
    try:
        return int(out)
    except ValueError:
        return 0


def _last_commit_iso(repo: Path) -> str:
    return _git(repo, "log", "-1", "--format=%cI")


def _count_files(path: Path, pattern: str) -> int:
    """Count matching files; -1 if path doesn't exist."""
    if not path.is_dir():
        return -1
    return sum(1 for _ in path.rglob(pattern))


def _count_loc(src_dir: Path) -> int:
    """Quick wc-style line count across .py files. -1 if no src dir."""
    if not src_dir.is_dir():
        return -1
    total = 0
    for f in src_dir.rglob("*.py"):
        try:
            total += sum(1 for _ in f.open(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return total


def _src_root(repo: Path, import_name: str) -> Path:
    """Best-effort src root: src/<pkg> if it exists, else repo/<pkg>."""
    cand = repo / "src" / import_name
    if cand.is_dir():
        return cand
    return repo / import_name


def _enrich_deep(state: PackageState) -> None:
    """Verbosity-3 columns: skills count, tests count, LOC.

    Filesystem-only — fast. MCP tools / py APIs would need package
    import, which is heavier; deferred.
    """
    repo = Path(state.local_path)
    if not repo.is_dir():
        return
    import_name = state.pkg.replace("-", "_")
    src_root = _src_root(repo, import_name)
    skills_root = src_root / "_skills"
    state.skills_count = _count_files(skills_root, "*.md")
    state.tests_count = _count_files(repo / "tests", "test_*.py")
    state.loc = _count_loc(src_root)


def _enrich_ci(state: PackageState) -> None:
    """Latest GH Actions test workflow conclusion on develop."""
    if not state.exists_locally:
        return
    try:
        out = subprocess.check_output(
            [
                "gh",
                "run",
                "list",
                "-R",
                f"ywatanabe1989/{state.pkg}",
                "--workflow=test.yml",
                "--branch=develop",
                "--limit=1",
                "--json=status,conclusion",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return
    import json as _json

    try:
        rows = _json.loads(out)
    except _json.JSONDecodeError:
        return
    if not rows:
        return
    row = rows[0]
    state.ci_status = row.get("conclusion") or row.get("status") or ""


def _compute_drift_local(version: str, tag: str) -> str:
    if not version or not tag:
        return ""
    if version == "(dynamic)":
        return "✓"  # scm-derived; tag IS the version
    tag_v = tag.lstrip("v")
    if tag_v == version:
        return "✓"
    return f"V={version} T={tag}"


def _compute_drift_pypi(tag: str, pypi: str) -> str:
    if not tag or not pypi:
        return ""
    tag_v = tag.lstrip("v")
    if tag_v == pypi:
        return "✓"
    return f"T={tag} P={pypi}"


def _ecosystem_packages() -> dict:
    """Read ECOSYSTEM dict; tolerant of older scitex-dev versions."""
    try:
        from scitex_dev._ecosystem._core import ECOSYSTEM
    except ImportError:
        return {}
    return dict(ECOSYSTEM)


def _gather_one(pkg: str, info: dict, verbosity: int) -> PackageState:
    raw_path = info.get("local_path", "")
    repo = Path(raw_path).expanduser() if raw_path else DEFAULT_PROJ_ROOT / pkg
    state = PackageState(
        pkg=pkg,
        category=info.get("category", ""),
        local_path=str(repo),
        exists_locally=repo.is_dir(),
    )
    if not state.exists_locally:
        return state

    state.version_pyproject, state.version_dynamic = _read_pyproject_version(repo)
    state.tag_latest = _latest_tag(repo)
    state.branch = _branch(repo)
    state.ahead = _ahead_of_origin(repo)
    state.last_commit_iso = _last_commit_iso(repo)
    state.has_audit_gate = _has_audit_gate(repo)
    state.skip_rules = _read_skip_rules(repo) if state.has_audit_gate else []
    state.drift_local = _compute_drift_local(state.version_pyproject, state.tag_latest)

    # Verbosity 2+: PyPI lookup. Deliberately not run here — networked.
    # The renderer can call _enrich_pypi(state) lazily / async per row.
    return state


def _enrich_pypi(state: PackageState) -> None:
    """Resolve PyPI latest version. Networked; cache 60s upstream."""
    try:
        out = subprocess.check_output(
            ["pip", "index", "versions", state.pkg],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return
    m = re.search(r"\(([^)]+)\)", out)
    if m:
        state.pypi_latest = m.group(1).strip()
        state.drift_pypi = _compute_drift_pypi(state.tag_latest, state.pypi_latest)


def gather_ecosystem_state(
    verbosity: int = 1,
    *,
    workers: int = 16,
    packages: list[str] | None = None,
) -> list[PackageState]:
    """Collect dashboard rows for every ECOSYSTEM package.

    Verbosity 0–1 are local-only (fast). Verbosity 2+ adds PyPI etc.
    """
    eco = _ecosystem_packages()
    if packages:
        eco = {k: v for k, v in eco.items() if k in packages}
    items = list(eco.items())

    with ThreadPoolExecutor(max_workers=workers) as pool:
        states = list(pool.map(lambda kv: _gather_one(kv[0], kv[1], verbosity), items))

    if verbosity >= 2:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pool.map(_enrich_pypi, states)

    return states
