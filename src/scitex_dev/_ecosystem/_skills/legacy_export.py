"""Legacy skill materializer, called only inside a validated temporary stage."""

from __future__ import annotations

import shutil
from pathlib import Path

from ._frontmatter import _stamp_frontmatter_field
from .skills import _generate_root_skill_md, list_skills


def export_unchecked(
    dest: Path,
    *,
    package: str | None = None,
    clean: bool = False,
    source: str = "installed",
    link: bool = False,
    force_copy: bool = False,
    _discover_fn=None,
    _root_fn=None,
    _version_fn=None,
) -> dict[str, list[Path]]:
    """Export skills to dest. Files are written as ``<dest>/<pkg-name>/SKILL.md``.

    Args:
        dest: Exact target directory. Required, no default.
        package: Export only this package. None exports all.
        clean: If True, delete each package subdirectory in dest before
               exporting. Default False (overwrite in place).
        source: "installed" (from locally installed packages) or "pypi"
                (download wheels from PyPI and extract _skills/).
        link: If True, symlink each skill file to its editable source
              (only valid with ``source="installed"``). Edits to the
              package source are then reflected in ``dest`` immediately
              without re-running export. Incompatible with ``source="pypi"``
              since PyPI wheels are extracted to a temp dir.

    Returns:
        Dict mapping package name -> list of exported file paths.
    """
    if link and force_copy:
        raise ValueError("link=True and force_copy=True are mutually exclusive")
    if link and source != "installed":
        raise ValueError("link=True requires source='installed'")

    if source == "pypi":
        from .skills_pypi import export_from_pypi

        return export_from_pypi(dest=dest, package=package)

    # REPORT duplicate dist-infos; never mutate site-packages from here.
    # Until 2026-07-29 this line called clean_stale_dist_info(), which
    # shutil.rmtree'd every dist-info but the newest-by-MTIME. Exporting
    # skills silently deleted package metadata across every site dir, and
    # mtime is not version ordering (`cp -p` preserves it, image builds stamp
    # it, an overlay lower layer carries the base image's) — so it could
    # delete the NEWER distribution's metadata and leave a package that
    # imports fine while reporting the wrong version. Independently of that:
    # on a container the target may sit in the READ-ONLY BASE LAYER, where
    # the delete only writes a whiteout that MASKS it — appearing to succeed
    # while silently changing a property (a whiteout-free overlay) that
    # agents check before a base-image swap. An export must not have a
    # destructive side effect on the environment; a warning is enough.
    from ..._core.dist_info import report_duplicate_dist_infos

    report_duplicate_dist_infos()

    all_skills = list_skills(
        package=package,
        _discover_fn=_discover_fn,
        _root_fn=_root_fn,
        _version_fn=_version_fn,
    )

    # Auto-detect editable installs: when source="installed" and --link
    # was not explicitly passed, check whether any discovered package is
    # installed in editable mode (pip install -e). If so, enable link
    # so source changes propagate immediately without re-export.
    if source == "installed" and not link and not force_copy:
        from ..._release.check_editable_drift import _editable_source_dir

        for pkg_name in all_skills:
            if _editable_source_dir(pkg_name) is not None:
                link = True
                break

    if clean:
        for pkg_name in all_skills:
            pkg_dir = dest / pkg_name
            # is_dir() follows symlinks; check is_symlink() first to
            # avoid rmtree-on-symlink errors when re-running with --link.
            if pkg_dir.is_symlink():
                pkg_dir.unlink()
            elif pkg_dir.is_dir():
                shutil.rmtree(pkg_dir)

    exported: dict[str, list[Path]] = {}

    for pkg_name, entries in all_skills.items():
        pkg_dest = dest / pkg_name

        # --link mode: symlink the entire package _skills/<pkg_name>/
        # directory (including nested subdirs) so any add/rename/delete
        # in source propagates immediately. Per-file symlinks (legacy)
        # miss new files until re-install.
        if link and entries:
            src_paths = [Path(e["path"]) for e in entries if Path(e["path"]).exists()]
            if src_paths:
                # Find canonical skill-tree root: walk up from any leaf
                # until we hit an ancestor named pkg_name. Handles both
                # flat layouts (one parent dir) and nested layouts like
                # general/03_interface/04_skills/12_quality-checklist.md.
                src_root = None
                for ancestor in [src_paths[0].parent, *src_paths[0].parents]:
                    if ancestor.name == pkg_name:
                        src_relative_root = ancestor
                        src_root = ancestor.resolve()
                        break
                if src_root and src_root.is_dir():
                    if pkg_dest.is_symlink() or pkg_dest.is_file():
                        pkg_dest.unlink()
                    elif pkg_dest.is_dir():
                        shutil.rmtree(pkg_dest)
                    pkg_dest.parent.mkdir(parents=True, exist_ok=True)
                    pkg_dest.symlink_to(src_root, target_is_directory=True)
                    exported[pkg_name] = [
                        pkg_dest / p.relative_to(src_relative_root) for p in src_paths
                    ]
                    continue
                # Could not resolve canonical root — fall through.

        pkg_dest.mkdir(parents=True, exist_ok=True)

        pkg_files: list[Path] = []
        for entry in entries:
            src_path = Path(entry["path"])
            if not src_path.exists():
                continue

            name = entry["name"]
            # Prefer `rel_path` (preserves nested subdirs like
            # `03_interface/04_skills/00_index.md`); fall back to flat
            # `<name>.md` for legacy entries that predate rel_path.
            rel_path = entry.get("rel_path")
            if rel_path:
                out_file = pkg_dest / rel_path
                out_file.parent.mkdir(parents=True, exist_ok=True)
            else:
                out_file = pkg_dest / ("SKILL.md" if name == "SKILL" else f"{name}.md")

            # Copy and flatten references/ paths in content
            content = src_path.read_text(encoding="utf-8")
            if name == "SKILL" and "references/" in content:
                import re

                content = re.sub(r"references/", "", content)

            # Stamp every leaf's frontmatter with the exporting package's
            # version + source. The cached copy is the single drift signal:
            # `skills get` / `skills list` compare these stamps to the
            # currently installed `importlib.metadata.version()` and warn
            # when the cache is older than what's installed.
            #
            # MANIFEST.md is forbidden by the SK-105 audit rule and is no
            # longer emitted; the per-leaf stamp replaces it.
            version = entry.get("version", "unknown")
            content = _stamp_frontmatter_field(content, "version", version)
            content = _stamp_frontmatter_field(content, "exported_via", source)

            if out_file.exists() or out_file.is_symlink():
                if out_file.is_symlink():
                    out_file.unlink()
                else:
                    out_file.chmod(0o644)

            if link:
                # Symlinking would defeat the per-leaf version stamp (the
                # source has no version field). Always write a stamped
                # copy when --link is requested AND a version stamp lands
                # in the content.
                out_file.write_text(content, encoding="utf-8")
            else:
                out_file.write_text(content, encoding="utf-8")
            pkg_files.append(out_file)

        if pkg_files:
            exported[pkg_name] = pkg_files

    # Generate root SKILL.md index
    _generate_root_skill_md(dest, exported)

    return exported
