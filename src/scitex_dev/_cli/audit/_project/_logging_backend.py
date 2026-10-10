"""Compatibility aliases for logging's exact stdlib backend proof."""

from scitex_logging._output_backend import (
    is_logging_backend_call,
    owns_logging_backend,
)

__all__ = ["is_logging_backend_call", "owns_logging_backend"]
