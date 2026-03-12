#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core Result type for LLM-friendly structured responses.

The Result type wraps function return values with metadata needed by
CLI and MCP consumers: success status, error codes, side effects,
next steps, and idempotency hints.

Python API users never see this type by default -- it is opt-in via
the ``return_as="result"`` parameter added by ``@supports_return_as``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    """Structured result wrapping function output with metadata.

    Attributes
    ----------
    success : bool
        Whether the operation succeeded.
    data : T | None
        The return value on success; None on failure.
    error : str | None
        Human-readable error message on failure.
    error_code : str | None
        Machine-readable error code (e.g. "E001").
    context : dict
        Additional context (file paths, parameters, etc.).
    side_effects : list[str]
        Description of mutations performed.
    next_steps : list[str]
        Suggested follow-up actions for the consumer.
    idempotent : bool
        Whether the operation is safe to retry.
    version : str | None
        API version for response schema evolution.
    """

    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    context: dict = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    idempotent: bool = False
    version: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to a plain dictionary, stripping None values."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @property
    def exit_code(self) -> int:
        """Map error_code to a CLI exit code."""
        if self.success:
            return 0
        return _error_code_to_exit(self.error_code)

    @classmethod
    def json_schema(cls) -> dict:
        """Return JSON Schema describing the Result envelope."""
        return dict(RESULT_SCHEMA)


RESULT_SCHEMA: dict = {
    "type": "object",
    "description": "Standardized Result envelope returned by all SciTeX MCP tools.",
    "properties": {
        "success": {
            "type": "boolean",
            "description": "Whether the operation succeeded.",
        },
        "data": {"description": "Tool-specific return value (any JSON type)."},
        "error": {
            "type": ["string", "null"],
            "description": "Human-readable error message.",
        },
        "error_code": {
            "type": ["string", "null"],
            "pattern": "^E\\d{3}$",
            "description": "Machine-readable error code (E001-E999).",
        },
        "context": {
            "type": "object",
            "description": "Additional context (file paths, params).",
        },
        "side_effects": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Mutations performed (file writes, network calls).",
        },
        "next_steps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Suggested follow-up actions.",
        },
        "idempotent": {"type": "boolean", "description": "Safe to retry?"},
        "version": {"type": ["string", "null"], "description": "API version."},
    },
    "required": ["success"],
}


def _error_code_to_exit(error_code: str | None) -> int:
    """Map an error code string to a CLI exit code."""
    _EXIT_MAP = {
        "E000": 0,
        "E001": 2,  # validation
        "E002": 1,  # file not found
        "E003": 4,  # permission
        "E004": 3,  # dependency
        "E005": 5,  # timeout
        "E006": 5,  # rate limited
        "E007": 1,  # network
        "E008": 2,  # config
        "E009": 6,  # conflict
        "E999": 1,  # internal
    }
    if error_code is None:
        return 1
    return _EXIT_MAP.get(error_code, 1)


# EOF
