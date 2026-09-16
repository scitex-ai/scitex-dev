"""Discover canonical package-local ``_skills`` trees."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable, Mapping

import scitex_logging as slogging

from ._model import RegistryIssue, RegistryReport, SkillRecord, sort_issues

_logger = slogging.getLogger(__name__)
_IGNORED_PARTS = {".git", "__pycache__"}


def hash_skill_tree(path: Path) -> str:
    """Hash relative names and bytes for every file in a skill tree."""

    if not path.is_dir():
        raise FileNotFoundError(f"skill target is not a directory: {path}")
    digest = hashlib.sha256()
    files = sorted(
        item
        for item in path.rglob("*")
        if item.is_file()
        and not any(part in _IGNORED_PARTS for part in item.relative_to(path).parts)
    )
    for item in files:
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = item.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _normalise_roots(
    package_roots: Mapping[str, os.PathLike[str] | str]
    | Iterable[os.PathLike[str] | str],
) -> list[tuple[str, Path]]:
    if isinstance(package_roots, Mapping):
        pairs = [(str(owner), Path(root)) for owner, root in package_roots.items()]
    else:
        paths = [Path(root) for root in package_roots]
        pairs = [(path.name, path) for path in paths]
    return sorted(pairs, key=lambda pair: (pair[0], str(pair[1])))


def discover_skills(
    package_roots: Mapping[str, os.PathLike[str] | str]
    | Iterable[os.PathLike[str] | str],
) -> RegistryReport:
    """Discover ``src/*/_skills/<name>`` candidates below explicit repos.

    Roots are explicit by design: adapters decide whether their source is an
    editable checkout, an installed distribution, or another inventory. A
    missing root, broken target, missing ``SKILL.md``, and duplicate name are
    findings rather than fallbacks.
    """

    records: list[SkillRecord] = []
    issues: list[RegistryIssue] = []
    for owner, repo_root in _normalise_roots(package_roots):
        if not repo_root.is_dir():
            issues.append(
                RegistryIssue(
                    "SR-101",
                    "missing",
                    owner,
                    repo_root,
                    "declared package root does not exist or is not a directory",
                )
            )
            continue
        skills_roots = sorted(repo_root.glob("src/*/_skills"), key=str)
        if not skills_roots:
            issues.append(
                RegistryIssue(
                    "SR-105",
                    "missing",
                    owner,
                    repo_root,
                    "declared package root has no src/*/_skills directory",
                )
            )
        for skills_root in skills_roots:
            for candidate in sorted(skills_root.iterdir(), key=lambda item: item.name):
                name = candidate.name
                if not candidate.is_dir():
                    if not candidate.is_symlink():
                        # Package-owned metadata (for example manifest.yaml) is
                        # not a skill candidate. Broken symlinks are candidates
                        # and must fail loud below.
                        continue
                    issues.append(
                        RegistryIssue(
                            "SR-102",
                            "broken",
                            name,
                            candidate,
                            "skill target is not a directory or is a broken symlink",
                        )
                    )
                    continue
                skill_file = candidate / "SKILL.md"
                if not skill_file.is_file():
                    issues.append(
                        RegistryIssue(
                            "SR-103",
                            "broken",
                            name,
                            skill_file,
                            "skill target has no regular SKILL.md",
                        )
                    )
                    continue
                records.append(
                    SkillRecord(
                        name=name,
                        owner=owner,
                        path=candidate.resolve(strict=True),
                        skill_file=skill_file.resolve(strict=True),
                        source_hash=hash_skill_tree(candidate),
                    )
                )

    names: dict[str, list[SkillRecord]] = {}
    for record in records:
        names.setdefault(record.name, []).append(record)
    for name, matches in names.items():
        if len(matches) > 1:
            for match in matches:
                issues.append(
                    RegistryIssue(
                        "SR-104",
                        "duplicate",
                        name,
                        match.path,
                        "skill name is provided by more than one package root",
                    )
                )

    ordered_records = tuple(
        sorted(records, key=lambda item: (item.name, item.owner, str(item.path)))
    )
    result = RegistryReport(ordered_records, sort_issues(issues))
    _logger.debug(
        "discovered %d package-local skill trees with %d findings",
        len(result.records),
        len(result.issues),
    )
    return result


__all__ = ["discover_skills", "hash_skill_tree"]
