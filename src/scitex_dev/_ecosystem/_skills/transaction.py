"""Stage, validate and promote shared skill installations without losing user files."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from ...skill_registry import (
    MANIFEST_NAME,
    RegistryIssue,
    RegistryReport,
    SkillRecord,
    audit_projection,
    hash_skill_tree,
)
from .projection_install import (
    ProjectionFinalizeResult,
    finalize_projection,
    registry_from_listing,
    registry_from_projection,
)


def _refused(registry, target, issues):
    audit = RegistryReport(registry.records, tuple(issues))
    return ProjectionFinalizeResult(registry, audit, None, None), {}


def _existing_registry(target: Path) -> RegistryReport:
    if not target.exists():
        return RegistryReport((), ())
    if not target.is_dir():
        raise ValueError("skills destination is not a directory")
    if not any(target.iterdir()):
        return RegistryReport((), ())
    manifest = target / MANIFEST_NAME
    if not manifest.is_file():
        raise ValueError(
            "existing nonempty skills destination has no ownership manifest"
        )
    document = json.loads(manifest.read_text(encoding="utf-8"))
    records = tuple(
        SkillRecord(
            item["name"],
            item["owner"],
            Path(item["source"]),
            Path(item["source"]) / "SKILL.md",
            item["source_hash"],
        )
        for item in document["skills"]
    )
    # The public auditor validates schema, digest, names, ownership and payloads.
    return audit_projection(RegistryReport(records, ()), target)


def _snapshot(target: Path):
    if not target.exists():
        return None
    return tuple(
        (
            item.name,
            str(item.resolve()),
            hash_skill_tree(item)
            if item.is_dir()
            else hashlib.sha256(item.read_bytes()).hexdigest(),
        )
        for item in sorted(target.iterdir())
    )


@contextmanager
def _locked_store(target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.parent / f".{target.name}.skills-install.lock"
    if lock.is_symlink():
        raise ValueError("skills install lock cannot be a symlink")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock, flags, 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("skills install lock must be an unshared regular file")
        if hasattr(os, "fchmod"):
            os.fchmod(handle.fileno(), 0o600)
        if os.name == "nt":
            import msvcrt

            if handle.seek(0, 2) == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _promote_projection(stage: Path, target: Path, backup: Path) -> None:
    """Restore the original directory when filesystem promotion fails."""
    if target.exists():
        target.rename(backup)
    try:
        stage.rename(target)
    except BaseException:
        if backup.exists():
            backup.rename(target)
        raise


def install_projection(
    dest: Path,
    *,
    package=None,
    clean=False,
    source="installed",
    link=False,
    force_copy=False,
    _discover_fn=None,
    _root_fn=None,
    _version_fn=None,
):
    """Preserve foreign content and unselected namespaces; never write a partial store."""
    from .skills import _export_skills_unchecked, _generate_root_skill_md, list_skills

    target = Path(dest).expanduser().resolve(strict=False)
    listed = (
        list_skills(
            package=package,
            _discover_fn=_discover_fn,
            _root_fn=_root_fn,
            _version_fn=_version_fn,
        )
        if source == "installed"
        else None
    )
    requested = (
        registry_from_listing(listed) if listed is not None else RegistryReport((), ())
    )
    if listed is not None and not requested.ok:
        return _refused(requested, target, requested.issues)
    if link and force_copy:
        raise ValueError("--link and --no-link cannot be combined")
    with _locked_store(target):
        try:
            previous = _existing_registry(target)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            issue = RegistryIssue("SI-200", "unmanaged", "*", target, str(exc))
            return _refused(requested, target, [issue])
        refresh = {item.name: item for item in requested.records}
        # A live canonical symlink can legitimately reflect new package bytes.
        # Refresh its stamp only when its current bytes equal the desired source.
        issues = []
        for issue in previous.issues:
            item = refresh.get(issue.name)
            entry = target / issue.name
            safe_refresh = (
                issue.code == "SP-402"
                and item is not None
                and entry.is_symlink()
                and entry.resolve() == item.path
                and hash_skill_tree(entry) == item.source_hash
            )
            if not safe_refresh:
                issues.append(issue)
        if issues:
            return _refused(requested, target, issues)
        before = _snapshot(target)
        with tempfile.TemporaryDirectory(
            prefix=f".{target.name}.install-", dir=target.parent
        ) as scratch:
            scratch = Path(scratch)
            expected_index = scratch / "expected-index"
            if (target / "SKILL.md").exists():
                expected_index.mkdir()
                _generate_root_skill_md(
                    expected_index, {item.name: () for item in previous.records}
                )
                expected = expected_index / "SKILL.md"
                if (
                    not expected.is_file()
                    or (target / "SKILL.md").read_bytes() != expected.read_bytes()
                ):
                    issue = RegistryIssue(
                        "SI-203",
                        "dirty",
                        "SKILL",
                        target / "SKILL.md",
                        "root skill index differs from the managed generated index",
                    )
                    return _refused(requested, target, [issue])
            stage = scratch / "projection"
            if target.exists():
                shutil.copytree(target, stage, symlinks=True)
            else:
                stage.mkdir()
            # Never write through an adapter-index symlink copied from the old store.
            staged_index = stage / "SKILL.md"
            if staged_index.is_symlink():
                staged_index.unlink()
            # Cleanup is confined to this owned temporary stage. The original
            # target is untouched until the entire combined projection audits.
            exported = _export_skills_unchecked(
                stage,
                package=package,
                clean=True,
                source=source,
                link=link,
                force_copy=force_copy,
                _discover_fn=_discover_fn,
                _root_fn=_root_fn,
                _version_fn=_version_fn,
            )
            desired = (
                requested
                if listed is not None
                else registry_from_projection(exported, stage)
            )
            if not desired.ok:
                return _refused(desired, target, desired.issues)
            combined = {item.name: item for item in previous.records}
            for item in desired.records:
                old = combined.get(item.name)
                if old is not None and old.owner != item.owner:
                    issue = RegistryIssue(
                        "SI-201",
                        "conflict",
                        item.name,
                        target / item.name,
                        "skill namespace belongs to another provider",
                    )
                    return _refused(desired, target, [issue])
                if source == "pypi":
                    item = replace(
                        item,
                        path=target / item.name,
                        skill_file=target / item.name / "SKILL.md",
                    )
                combined[item.name] = item
            registry = RegistryReport(
                tuple(combined[name] for name in sorted(combined)), ()
            )
            _generate_root_skill_md(stage, {name: () for name in combined})
            finalized = finalize_projection(registry, stage, "scitex-dev")
            if not finalized.audit.ok:
                return finalized, {}
            if _snapshot(target) != before:
                issue = RegistryIssue(
                    "SI-202",
                    "changed",
                    "*",
                    target,
                    "skills destination changed during installation",
                )
                return _refused(registry, target, [issue])
            backup = scratch / "previous"
            _promote_projection(stage, target, backup)
            # This audit is read-only and names the actual promoted destination.
            try:
                audited = audit_projection(registry, target)
            except BaseException:
                target.rename(stage)
                if backup.exists():
                    backup.rename(target)
                raise
            if not audited.ok:
                target.rename(stage)
                if backup.exists():
                    backup.rename(target)
                return _refused(registry, target, audited.issues)
            final = replace(
                finalized, audit=audited, manifest_path=target / MANIFEST_NAME
            )
            relocated = {
                name: [target / path.relative_to(stage) for path in paths]
                for name, paths in exported.items()
            }
            return final, relocated
