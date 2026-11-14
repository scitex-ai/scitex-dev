"""Check regular parent-package and target files against one owner's manifest.

This never imports code. RECORD consistency is distinct from publisher trust,
exclusive file ownership, actual import origins and behavioral qualification.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .._core.provider_metadata import ProviderMetadata
from ._capability_resolution import _provider_record_context, _resolve_recorded_file


def resolve_capability_provider_chain(
    provider: ProviderMetadata, *, path: Sequence[str | Path] | None = None,
) -> tuple[Path, ...]:
    """Verify regular parent package files and target against one owner's RECORD.

    Return canonical files from outermost parent to target. Namespace parents,
    unrecorded/editable parents and files claimed only by other distributions
    remain unqualified. This is manifest consistency, not publisher trust,
    actual import-origin verification, code execution or transactional state.
    """
    dist, rows = _provider_record_context(provider, path=path)
    parts = provider.target.partition(":")[0].split(".")
    result = []
    for length in range(1, len(parts)):
        parent = Path(*parts[:length]) / "__init__.py"
        try:
            result.append(_resolve_recorded_file(dist, rows, {parent.as_posix()}))
        except ValueError as exc:
            raise ValueError(f"parent package {'.'.join(parts[:length])}: {exc}") from exc
    relative = Path(*parts)
    result.append(_resolve_recorded_file(dist, rows, {
        relative.with_suffix(".py").as_posix(),
        (relative / "__init__.py").as_posix(),
    }))
    return tuple(result)
