"""Read-only, scoped checks of documented Python against local source."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable, Optional

from ._source_references import _check_reference, _read

_LIMITATIONS = [
    "Only top-level closed Markdown python/py fences are parsed; "
    "prose, RST and other languages are not checked.",
    "Local src-layout modules, direct definitions and explicit local "
    "from-import chains are checked statically, "
    "without importing or running code.",
    "Local chains are bounded to 32 references. Cycles, ambiguous/conditional "
    "bindings, star imports and relative example imports remain unverified.",
    "Dynamic attributes, external imports, signatures, example "
    "results and CLI/MCP/Web API behavior are not verified.",
    "Installed/exported skills are not read, compared or refreshed; "
    "this is not complete documentation drift coverage.",
]


def _python_blocks(text: str):
    """Yield code and source line for closed Python fences only."""
    fence = None
    code = []
    start = 0
    indent = 0
    for line_no, line in enumerate(text.splitlines(), 1):
        if fence is None:
            match = re.match(r"^ {0,3}(`{3,}|~{3,})([^`~]*)$", line)
            if match:
                fence = match[1]
                indent = len(line) - len(line.lstrip(" "))
                language = match[2].strip().lower()
                start = line_no + 1 if language in {"python", "py"} else 0
                code = []
        elif re.fullmatch(
            r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", line
        ):
            if start:
                yield start, "\n".join(code)
            fence = None
        elif start:
            leading = len(line) - len(line.lstrip(" "))
            code.append(line[min(indent, leading) :])
    if fence is not None and start:
        raise ValueError(f"unclosed Python fence at line {start - 1}")


def _readme_version(root: Path, documents: dict[Path, str]):
    readme = root / "README.md"
    if readme not in documents:
        return None, "not_checked", None
    claim = re.search(
        r"(?im)^\s*(?:\*\*)?version(?:\*\*)?\s*:\s*v?([0-9][\w.+-]*)",
        documents[readme],
    )
    if not claim:
        return None, "not_present", None
    try:
        import tomllib
    except ImportError:  # Python 3.9/3.10, a declared core dependency.
        import tomli as tomllib
    data = tomllib.loads(_read(root / "pyproject.toml", root))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str):
        return None, "not_checked", "project version is dynamic or absent"
    match = claim[1] == version
    return (
        match,
        "match" if match else "mismatch",
        (
            None
            if match
            else f"README Version: {claim[1]} differs from project version {version}"
        ),
    )


def verify_docs_and_skills(
    package_path: Optional[Path] = None,
    *,
    documents: Optional[Iterable[Path]] = None,
) -> dict:
    """Check selected Markdown statically, without exports, imports or execution.

    Defaults to README.md and src/*/_skills/**/*.md in the selected package.
    Pass ``documents=[Path('docs/guide.md')]`` to check explicit Markdown files
    within that root. Top-level Python/py fences are parsed; local src-layout import
    modules, direct definitions and explicit local from-import chains are checked.
    Cyclic, overlong, ambiguous, conditional, dynamic and external references
    remain unverified. Only an explicit ``Version: X`` README line
    is compared with a literal project.version; no version mention is required.

    Legacy keys remain, but readme_version_match and skills_stale can be None
    when not checked. Status is needs_update for failures, incomplete for
    unverified references/no Python blocks, otherwise ok *within checked_scope*.
    Always inspect checked_scope, unverified and limitations. Export staleness,
    signatures, runtime results and other interface/documentation drift are
    deliberately not claimed. No installed skills or user-home paths are used.
    """
    root = Path(package_path or Path.cwd()).resolve()
    selected = (
        [root / "README.md", *sorted(root.glob("src/*/_skills/**/*.md"))]
        if documents is None
        else [root / Path(path) for path in documents]
    )
    issues, unverified, stale_files, checked_imports = [], [], set(), []
    contents = {}
    blocks = 0
    for path in dict.fromkeys(selected):
        try:
            if path.suffix.lower() != ".md":
                raise ValueError("only Markdown documents are supported")
            content = _read(path, root)
            contents[path] = content
            for start, code in _python_blocks(content):
                blocks += 1
                tree = ast.parse(code, filename=str(path))
                for node in ast.walk(tree):
                    references = []
                    if isinstance(node, ast.Import):
                        references = [(alias.name, None) for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        if node.level:
                            unverified.append(
                                f"{path}:{start + node.lineno - 1}: "
                                "relative example import"
                            )
                            continue
                        references = [
                            (node.module or "", alias.name) for alias in node.names
                        ]
                    for module, name in references:
                        reference = module + ("." + name if name else "")
                        where = f"{path}:{start + node.lineno - 1}: {reference}"
                        state, detail = _check_reference(root, module, name)
                        if state == "checked":
                            checked_imports.append(where)
                        elif state == "issue":
                            issues.append(f"{where}: {detail}")
                            stale_files.add(str(path))
                        else:
                            unverified.append(f"{where}: {detail}")
        except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
            issues.append(f"{path}: {type(exc).__name__}: {exc}")
            stale_files.add(str(path))
    try:
        version_match, version_check, detail = _readme_version(root, contents)
        if detail:
            (unverified if version_match is None else issues).append(detail)
    except (OSError, UnicodeError, ValueError) as exc:
        version_match, version_check = None, "failed"
        issues.append(f"README version check: {type(exc).__name__}: {exc}")
    if not selected:
        issues.append("No documents selected")
    if not blocks:
        unverified.append("No Python/py fenced blocks were checked")
    skill_files = [str(path) for path in selected if "_skills" in path.parts]
    return {
        "skills_stale": (
            True
            if stale_files.intersection(skill_files)
            else (None if not skill_files or unverified else False)
        ),
        "stale_files": sorted(stale_files),
        "readme_version_match": version_match,
        "readme_version_check": version_check,
        "issues": issues,
        "status": "needs_update" if issues else "incomplete" if unverified else "ok",
        "checked_scope": {
            "package_path": str(root),
            "documents": [str(path) for path in contents],
            "python_blocks": blocks,
            "imports": checked_imports,
        },
        "unverified": unverified,
        "export_staleness": "not_checked",
        "limitations": list(_LIMITATIONS),
    }
