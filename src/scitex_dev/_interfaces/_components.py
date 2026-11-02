"""Bounded owned component namespaces, not a package or live-host registry."""

from __future__ import annotations

import os
from pathlib import Path

from ._source import UnprovenBinding

_EXCLUDED = frozenset(
    {
        "tests",
        "test",
        "testdata",
        "fixtures",
        "examples",
        "vendor",
        "vendored",
        "templates",
        "static",
        "assets",
        "node_modules",
        "build",
        "dist",
        "docs",
        "_skills",
        "_sphinx_html",
        "__pycache__",
    }
)


def component_modules(source, module):
    """Yield package/component roots at depth <=4; never follow directory links."""
    path, _tree = source.module(module)
    if path.name != "__init__.py":
        return
    root = path.parent
    if source.overlays is not None:
        prefix = root.relative_to(source.repo).as_posix() + "/"
        names = set()
        for name in source.overlays:
            if not name.startswith(prefix) or not name.endswith("/__init__.py"):
                continue
            parts = name[len(prefix) :].split("/")[:-1]
            if len(parts) <= 4 and all(
                part.isidentifier()
                and part not in _EXCLUDED
                and part.lstrip("_") not in _EXCLUDED
                for part in parts
            ):
                names.add(".".join((module, *parts)))
        if len(names) > 512:
            raise UnprovenBinding("component source inventory exceeds 512 namespaces")
        yield from sorted(names)
        return
    for count, (current, directories, files) in enumerate(
        os.walk(root, followlinks=False), 1
    ):
        relative = Path(current).relative_to(root)
        parts = relative.parts
        directories[:] = sorted(
            name
            for name in directories
            if name.isidentifier()
            and not name.startswith(".")
            and name not in _EXCLUDED
            and name.lstrip("_") not in _EXCLUDED
            and not (Path(current) / name).is_symlink()
            and len(parts) < 4
        )
        if count > 512:
            raise UnprovenBinding("component source inventory exceeds 512 namespaces")
        if parts and "__init__.py" in files:
            candidate = ".".join((module, *parts))
            try:
                source.module(candidate)
            except UnprovenBinding:
                continue
            yield candidate
