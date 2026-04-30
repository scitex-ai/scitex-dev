"""Optional-import helper for SciTeX standalone packages.

Use in a `__init__.py` to replace inline `try/except ImportError` blocks:

    from scitex_dev import try_import_optional

    h5py = try_import_optional("h5py", extra="hdf5", pkg="scitex-io")
    ndarray = try_import_optional("numpy", attr="ndarray")  # always installed
    rel_mod = try_import_optional(".sub.thing", package="scitex_io")

Returns the imported object on success and ``None`` on ``ImportError``.
The original failure (module name + extra/pkg metadata) is recorded on the
returned ``None`` is impossible — instead, callers can read the registry via
``last_install_hint(name)`` to construct precise error messages at the
use-site without re-raising.

The `NotInstalled` sentinel proposal (see python-api skill TODO.md) is
deferred — Pattern A (`X = None` always present in `__all__`) plus a
companion `XXX_AVAILABLE = X is not None` flag covers all current use cases.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

__all__ = ["try_import_optional", "last_install_hint", "InstallHint"]


@dataclass(frozen=True)
class InstallHint:
    """Metadata to help a caller surface a useful install message."""

    module: str
    extra: str | None
    pkg: str | None

    def message(self) -> str:
        if self.pkg and self.extra:
            return (
                f"`{self.module}` is required. "
                f"Install with: pip install '{self.pkg}[{self.extra}]'"
            )
        if self.extra:
            return (
                f"`{self.module}` is required. "
                f"Re-install with the '{self.extra}' extra."
            )
        return f"`{self.module}` is required. Install with: pip install {self.module}"


_HINTS: dict[str, InstallHint] = {}


def last_install_hint(name: str) -> InstallHint | None:
    """Return the most recently recorded install hint for ``name`` (or ``None``)."""
    return _HINTS.get(name)


def try_import_optional(
    module_path: str,
    attr: str | None = None,
    *,
    extra: str | None = None,
    pkg: str | None = None,
    package: str | None = None,
) -> Any:
    """Import ``module_path``; return ``None`` on ``ImportError``.

    Parameters
    ----------
    module_path : str
        Module to import. Leading ``.`` triggers relative resolution against
        ``package`` (mirrors :func:`importlib.import_module`).
    attr : str, optional
        If given, return ``getattr(module, attr)`` instead of the module.
        A missing attribute is treated identically to a failed import.
    extra : str, optional
        Name of the pip extra that pulls this dependency (used for the
        install hint surfaced via :func:`last_install_hint`).
    pkg : str, optional
        Distribution name owning the extra (e.g. ``"scitex-io"``).
    package : str, optional
        Anchor for relative imports.

    Returns
    -------
    object or None
        The imported module/attribute, or ``None`` on failure.
    """
    if module_path.startswith(".") and package is None:
        raise ValueError(
            "relative imports require an explicit `package=` argument "
            f"(got module_path={module_path!r})"
        )
    try:
        mod = importlib.import_module(module_path, package=package)
    except ImportError:
        _HINTS[module_path] = InstallHint(module=module_path, extra=extra, pkg=pkg)
        return None

    if attr is None:
        return mod
    try:
        return getattr(mod, attr)
    except AttributeError:
        _HINTS[module_path] = InstallHint(module=module_path, extra=extra, pkg=pkg)
        return None
