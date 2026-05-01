"""SciTeX-dev CLI: ecosystem command group.

`_registry` — `scitex-dev ecosystem` Click commands (versions, sync, audit-*).
"""

from ._registry import register_ecosystem_commands

__all__ = ["register_ecosystem_commands"]
