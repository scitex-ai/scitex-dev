#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Error code registry for LLM-friendly error categorization.

Provides machine-readable error codes that map to CLI exit codes
and guide LLM error recovery.
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Machine-readable error codes for structured error responses."""

    OK = "E000"
    VALIDATION = "E001"
    FILE_NOT_FOUND = "E002"
    PERMISSION = "E003"
    DEPENDENCY = "E004"
    TIMEOUT = "E005"
    RATE_LIMITED = "E006"
    NETWORK = "E007"
    CONFIG = "E008"
    CONFLICT = "E009"
    INTERNAL = "E999"

    @property
    def exit_code(self) -> int:
        """POSIX-style exit code for this error category."""
        return _EXIT_CODES.get(self, 1)


_EXIT_CODES = {
    ErrorCode.OK: 0,
    ErrorCode.VALIDATION: 2,
    ErrorCode.FILE_NOT_FOUND: 1,
    ErrorCode.PERMISSION: 4,
    ErrorCode.DEPENDENCY: 3,
    ErrorCode.TIMEOUT: 5,
    ErrorCode.RATE_LIMITED: 5,
    ErrorCode.NETWORK: 1,
    ErrorCode.CONFIG: 2,
    ErrorCode.CONFLICT: 6,
    ErrorCode.INTERNAL: 1,
}

_BUILTIN_ERROR_MAP: dict[type, ErrorCode] = {
    FileNotFoundError: ErrorCode.FILE_NOT_FOUND,
    PermissionError: ErrorCode.PERMISSION,
    TimeoutError: ErrorCode.TIMEOUT,
    ConnectionError: ErrorCode.NETWORK,
    ImportError: ErrorCode.DEPENDENCY,
    ValueError: ErrorCode.VALIDATION,
    TypeError: ErrorCode.VALIDATION,
    KeyError: ErrorCode.CONFIG,
}


def classify_exception(exc: Exception) -> ErrorCode:
    """Classify an exception into an ErrorCode.

    Checks for a ``.error_code`` attribute first (SciTeXError convention),
    then falls back to built-in exception type mapping.
    """
    code = getattr(exc, "error_code", None)
    if code is not None:
        if isinstance(code, ErrorCode):
            return code
        if isinstance(code, str):
            try:
                return ErrorCode(code)
            except ValueError:
                pass

    for exc_type, error_code in _BUILTIN_ERROR_MAP.items():
        if isinstance(exc, exc_type):
            return error_code

    return ErrorCode.INTERNAL


# EOF
