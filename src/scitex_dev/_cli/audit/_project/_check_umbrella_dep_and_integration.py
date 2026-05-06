"""PS139 + PS140 — umbrella-dep ban + cross-package integration gate.

PS139: standalone packages must not list `scitex` (the umbrella) in
runtime / extras dependencies. Codified after the 2026-05-06 HPC NFS
slow-import investigation surfaced 35+ standalones that pulled the
umbrella as a transitive dep.

PS140: any package whose source has cross-package imports
(`scitex_<X>` peer or `scitex.<X>` umbrella) must ship a runtime
gate at `tests/integration/test_cross_package_imports.py` listing
every cross-package module name. Without it, renames/moves in peer
standalones surface as silent ModuleNotFoundError at user runtime
(this is exactly how the `scitex_io._load_cache` rename slipped past
CI for weeks).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


_UMBRELLA_DEP_RE = re.compile(r"^\s*scitex(\[[^\]]*\])?\s*([<>=!~,].*)?$")


def _own_import_name(repo: Path) -> str:
    """`scitex-foo` → `scitex_foo`."""
    return repo.name.replace("-", "_")


def _strip_specifier(spec: str) -> str:
    """`scitex>=2.0` → `scitex`, `scitex[all]>=2.19` → `scitex`."""
    s = spec.strip().strip('"').strip("'")
    s = re.split(r"[<>=!~,;\[\s]", s, maxsplit=1)[0]
    return s.strip()


def _scan_pyproject_for_umbrella(pyproject: Path) -> list[str]:
    """Return human descriptions of each `scitex` (umbrella) entry found."""
    findings: list[str] = []
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return findings
    project = data.get("project", {})
    for spec in project.get("dependencies", []) or []:
        name = _strip_specifier(spec)
        if name == "scitex":
            findings.append(f"[project.dependencies] -> {spec!r}")
    for extra, members in (project.get("optional-dependencies", {}) or {}).items():
        for spec in members or []:
            name = _strip_specifier(spec)
            if name == "scitex":
                findings.append(f"[project.optional-dependencies.{extra}] -> {spec!r}")
    return findings


def _collect_cross_package_imports(src_root: Path, own_import: str) -> set[str]:
    """Mirror `/tmp/write-integration-tests.py` so the gate stays in sync."""
    seen: set[str] = set()
    for py in src_root.rglob("*.py"):
        if any(s in py.parts for s in ("__pycache__", "build", "dist", ".tox")):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if (
                    mod == "scitex"
                    or mod.startswith("scitex.")
                    or mod.startswith("scitex_")
                ):
                    if mod == own_import or mod.startswith(own_import + "."):
                        continue
                    seen.add(mod)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if (
                        name == "scitex"
                        or name.startswith("scitex.")
                        or name.startswith("scitex_")
                    ):
                        if name == own_import or name.startswith(own_import + "."):
                            continue
                        seen.add(name)
    return seen


def _read_declared_imports(test_file: Path) -> set[str]:
    try:
        tree = ast.parse(test_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "CROSS_PACKAGE_IMPORTS":
                    if isinstance(node.value, ast.List):
                        return {
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant)
                            and isinstance(elt.value, str)
                        }
    return set()


def check_ps139_umbrella_dep(repo: Path, violation_cls: type, out: list) -> None:
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        return
    own = _own_import_name(repo)
    # Exempt the umbrella package itself.
    if own == "scitex":
        return
    findings = _scan_pyproject_for_umbrella(pyproject)
    for f in findings:
        out.append(
            violation_cls(
                "PS139",
                str(pyproject),
                f"`scitex` (umbrella) listed at {f}; replace with peer "
                "standalone(s) to avoid the umbrella drag.",
            )
        )


def check_ps140_integration_gate(
    repo: Path, distribution: str, violation_cls: type, out: list
) -> None:
    own = _own_import_name(repo)
    if own == "scitex":
        # Umbrella has its own integration test; no peer-cross expected.
        pass
    src_root = repo / "src"
    if not src_root.exists():
        return
    expected = _collect_cross_package_imports(src_root, own)
    if not expected:
        return  # No cross-package imports — gate not required.
    test_file = repo / "tests" / "integration" / "test_cross_package_imports.py"
    if not test_file.exists():
        out.append(
            violation_cls(
                "PS140",
                str(repo),
                (
                    f"source has {len(expected)} cross-package import(s) "
                    f"(e.g. {sorted(expected)[:3]}) but no "
                    "`tests/integration/test_cross_package_imports.py` "
                    "runtime gate."
                ),
            )
        )
        return
    declared = _read_declared_imports(test_file)
    missing = expected - declared
    extra = declared - expected
    if missing or extra:
        msg_parts = []
        if missing:
            msg_parts.append(
                f"missing from gate: {sorted(missing)[:5]}"
                + ("…" if len(missing) > 5 else "")
            )
        if extra:
            msg_parts.append(
                f"stale in gate: {sorted(extra)[:5]}" + ("…" if len(extra) > 5 else "")
            )
        out.append(
            violation_cls(
                "PS140",
                str(test_file),
                "; ".join(msg_parts) + ". Regenerate the gate.",
            )
        )
