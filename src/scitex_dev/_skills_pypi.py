#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export skills from PyPI wheels (no local install required).

Downloads each scitex wheel with --no-deps, extracts _skills/**/*.md,
and writes them to the target directory.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def export_from_pypi(
    dest: Path,
    package: Optional[str] = None,
) -> dict[str, list[Path]]:
    """Download wheels from PyPI and extract _skills/ markdown files.

    Args:
        dest: Target directory (should end with ``scitex/``).
        package: Export only this package. None exports all known packages.

    Returns:
        Dict mapping namespace -> list of exported file paths.
    """
    from .ecosystem import get_all_packages

    all_packages = get_all_packages()
    if package:
        all_packages = [p for p in all_packages if p == package]

    exported: dict[str, list[Path]] = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for pip_name in all_packages:
            pkg_tmp = tmp / pip_name
            pkg_tmp.mkdir()

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    pip_name,
                    "--no-deps",
                    "--only-binary=:all:",
                    "-d",
                    str(pkg_tmp),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.info("Skipping %s: not on PyPI or no wheel", pip_name)
                continue

            wheels = list(pkg_tmp.glob("*.whl"))
            if not wheels:
                continue

            pkg_files: list[Path] = []
            with zipfile.ZipFile(wheels[0]) as zf:
                for name in zf.namelist():
                    if "/_skills/" not in name or not name.endswith(".md"):
                        continue
                    parts = name.split("/_skills/", 1)
                    if len(parts) != 2:
                        continue
                    rel_path = parts[1]
                    out_path = dest / rel_path
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    if out_path.exists():
                        out_path.chmod(0o644)
                    out_path.write_bytes(zf.read(name))
                    pkg_files.append(out_path)

            if pkg_files:
                ns_groups: dict[str, list[Path]] = {}
                for f in pkg_files:
                    ns = f.parent.name
                    ns_groups.setdefault(ns, []).append(f)
                exported.update(ns_groups)

    # Generate root SKILL.md index
    from .skills import _generate_root_skill_md

    _generate_root_skill_md(dest, exported)

    return exported


# EOF
