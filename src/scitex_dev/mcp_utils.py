#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP utilities for consuming Result objects."""

from __future__ import annotations

from typing import Any, Callable

from .types import Result


def run_as_mcp(fn: Callable, **kwargs: Any) -> str:
    """Call a ``@supports_return_as`` function and return MCP-ready JSON.

    Parameters
    ----------
    fn : Callable
        A function decorated with ``@supports_return_as``.
    **kwargs
        Arguments to pass to ``fn``.

    Returns
    -------
    str
        JSON string with the full Result structure.
    """
    result = fn(**kwargs, return_as="result")
    return result.to_json()


def result_to_mcp(result: Result) -> str:
    """Convert an existing Result to MCP-ready JSON."""
    return result.to_json()


# EOF
