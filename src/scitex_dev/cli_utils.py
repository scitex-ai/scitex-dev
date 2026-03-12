#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI utilities for consuming Result objects."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from .types import Result


def handle_result(
    result: Result,
    as_json: bool = False,
    file: Any = None,
) -> int:
    """Format and print a Result, return the exit code.

    Parameters
    ----------
    result : Result
        The structured result to display.
    as_json : bool
        If True, output full JSON. If False, human-friendly text.
    file : file-like | None
        Output stream. Defaults to stdout/stderr based on success.

    Returns
    -------
    int
        Exit code suitable for ``sys.exit()``.
    """
    if as_json:
        out = file or sys.stdout
        print(result.to_json(), file=out)
    elif result.success:
        out = file or sys.stdout
        data = result.data
        if isinstance(data, (dict, list, tuple)):
            print(json.dumps(data, indent=2, default=str), file=out)
        else:
            print(data, file=out)
    else:
        out = file or sys.stderr
        print(f"Error: {result.error}", file=out)
        if result.next_steps:
            print("", file=out)
            for step in result.next_steps:
                print(f"  - {step}", file=out)

    return result.exit_code


def run_as_cli(
    fn: Callable,
    as_json: bool = False,
    **kwargs: Any,
) -> None:
    """Call a ``@supports_return_as`` function and exit with proper code.

    Parameters
    ----------
    fn : Callable
        A function decorated with ``@supports_return_as``.
    as_json : bool
        If True, output full JSON.
    **kwargs
        Arguments to pass to ``fn``.
    """
    result = fn(**kwargs, return_as="result")
    code = handle_result(result, as_json=as_json)
    sys.exit(code)


# EOF
