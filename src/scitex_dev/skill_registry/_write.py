"""Atomic persistence for generated skill-projection manifests."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable

from ._model import SkillRecord
from ._projection import MANIFEST_NAME, build_projection_manifest


def write_projection_manifest(
    records: Iterable[SkillRecord], adapter: str, projection_root: Path
) -> tuple[Path, dict[str, object]]:
    """Atomically persist and return a manifest for materialized records."""

    projection_root = projection_root.resolve(strict=True)
    records = tuple(records)
    document = build_projection_manifest(
        records, adapter, projection_root=projection_root
    )
    content = json.dumps(document, indent=2, sort_keys=True) + "\n"
    manifest_path = projection_root / MANIFEST_NAME
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=projection_root,
            prefix=f".{MANIFEST_NAME}.",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, manifest_path)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return manifest_path, document


__all__ = ["write_projection_manifest"]
