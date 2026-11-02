"""Preserve the declared test runtime in isolated children, never ambient paths.

The canonical native driver installs into $TMPDIR/site using --target. -I
correctly ignores PYTHONPATH, so a test child needs that one attested site
explicitly. This helper is test-only: no production import path is changed.
"""

from __future__ import annotations

import os
import stat
import sys
import sysconfig
from importlib import metadata
from pathlib import Path


class ChildRuntimeError(RuntimeError):
    """The parent runtime cannot safely be reproduced for a test child."""


def _owned_directory(path, *, private=False):
    if not path.is_absolute() or path.resolve() != path:
        raise ChildRuntimeError(
            "Test runtime directories must be physical absolute paths"
        )
    try:
        info = path.lstat()
    except OSError as exc:
        raise ChildRuntimeError("Test runtime directory is unavailable") from exc
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ChildRuntimeError(
            "Test target directories must belong to the current user"
        )
    if info.st_mode & 0o022 or (private and stat.S_IMODE(info.st_mode) != 0o700):
        raise ChildRuntimeError(
            "Test runtime directory permissions are not private enough"
        )


def _trusted_target_site(scratch, *, environment, parent_paths):
    scratch = Path(scratch)
    _owned_directory(scratch, private=True)
    target = scratch / "site"
    _owned_directory(target)
    if environment.get("PYTHONNOUSERSITE") != "1":
        raise ChildRuntimeError("Native tests must disable foreign user-site packages")
    if target not in {Path(path).resolve() for path in parent_paths if path}:
        raise ChildRuntimeError(
            "The owned target site is not selected by the parent runtime"
        )
    return target


def child_runtime_paths(source_root, *, required_distributions):
    """Return only the actual Dev source and an attested native --target site.

    No environment-supplied PYTHONPATH entries are copied. Metadata for each
    required dependency must resolve inside the interpreter's own normal site,
    or the exact canonical owned target. No .pth files are evaluated here.
    """
    source = Path(source_root).resolve()
    imported = sys.modules.get("scitex_dev")
    origin = Path(getattr(imported, "__file__", "")).resolve()
    if origin != source / "scitex_dev" / "__init__.py":
        raise ChildRuntimeError(
            "Test source does not match the parent's actual Dev import"
        )
    standard_sites = {
        Path(sysconfig.get_path(key)).resolve() for key in ("purelib", "platlib")
    }
    supplemental = None
    for name in required_distributions:
        try:
            location = Path(metadata.distribution(name).locate_file("")).resolve()
        except metadata.PackageNotFoundError as exc:
            raise ChildRuntimeError(
                f"Declared test dependency {name!r} is not installed"
            ) from exc
        if location in standard_sites:
            continue
        # Setuptools may expose this checkout's own .egg-info on source/src.
        # That does not authorize another package or any other source root.
        if name.replace("_", "-").lower() == "scitex-dev" and location == source:
            continue
        raw = os.environ.get("TMPDIR")
        if not raw or location != Path(raw) / "site":
            raise ChildRuntimeError(
                "Declared test dependency resolves outside the owned runtime"
            )
        candidate = _trusted_target_site(
            Path(raw), environment=os.environ, parent_paths=sys.path
        )
        if location != candidate:
            raise ChildRuntimeError("Selected dependency and target site do not agree")
        supplemental = candidate
    return [str(source), *([str(supplemental)] if supplemental is not None else [])]
