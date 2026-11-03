"""Inert installed documentation-provider metadata for dispatcher consumers.

Leaf ``scitex_dev.docs`` declarations are authoritative. Reading this catalog
never loads entry points, imports their targets, executes handlers or adds a
registry fallback. It establishes installed declaration, not live availability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .._core.provider_metadata import ProviderMetadata, read_provider_metadata

# Keep the public documentation type name while sharing metadata ownership with
# other provider groups. Both names denote the same immutable row contract.
DocProvider = ProviderMetadata

__all__ = ["DocProvider", "list_doc_providers"]


def list_doc_providers(
    *, path: Sequence[str | Path] | None = None
) -> tuple[DocProvider, ...]:
    """Read installed docs declarations, preserving duplicate names.

    ``path`` restricts discovery to explicit metadata directories. Without it,
    use importlib's installed distribution search. Missing versions remain
    unknown; invalid metadata raises rather than certifying an incomplete list.
    """
    return read_provider_metadata("scitex_dev.docs", path=path)
