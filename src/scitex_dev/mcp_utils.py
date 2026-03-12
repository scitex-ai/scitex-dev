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


def wrap_as_mcp(fn: Callable, **kwargs: Any) -> str:
    """Call any function and wrap its return in Result JSON.

    Unlike ``run_as_mcp`` (which requires ``@supports_return_as``),
    this wraps any plain function. Use this to retrofit existing
    handlers without modifying the underlying function.

    Parameters
    ----------
    fn : Callable
        Any callable returning data or raising exceptions.
    **kwargs
        Arguments to pass to ``fn``.

    Returns
    -------
    str
        JSON string with Result structure.
    """
    from .errors import classify_exception

    try:
        data = fn(**kwargs)
        return Result(success=True, data=data).to_json()
    except Exception as exc:
        error_code = classify_exception(exc)
        next_steps = []
        suggestion = getattr(exc, "suggestion", None)
        if suggestion:
            next_steps.append(suggestion)
        suggestions = getattr(exc, "suggestions", None)
        if suggestions and isinstance(suggestions, list):
            next_steps.extend(suggestions)
        context = getattr(exc, "context", {})
        return Result(
            success=False,
            error=str(exc),
            error_code=error_code.value,
            context=context if isinstance(context, dict) else {},
            next_steps=next_steps,
        ).to_json()


def result_to_mcp(result: Result) -> str:
    """Convert an existing Result to MCP-ready JSON."""
    return result.to_json()


# EOF
