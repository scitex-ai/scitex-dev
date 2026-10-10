#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stable developer-tooling wrappers around logging-owned output transport.

Diagnostics use stderr loggers, human output uses formatted stdout consoles,
and exact payloads use ``getPlainConsole().emit``. These wrappers retain their
caller-stream and newline contracts while transport remains with logging.
"""

from __future__ import annotations

from typing import TextIO

__all__ = ["render_content", "render_rich", "write_stream"]


def render_content(content: str) -> None:
    """Print caller-supplied, already-rendered content verbatim to stdout.

    This output operation delegates to logging's plain console and emits
    caller-supplied content unchanged. It exists for the handful of product
    outputs whose exact bytes are a published contract — ``scitex-dev
    --version`` (pinned by tests and parsed by the fleet), a shell completion
    script that gets ``source``d — where a logging level prefix or a hop to
    stderr would corrupt the payload rather than clarify it.

    It is NOT a general ``print`` hatch: human-facing status and diagnostics
    belong on ``scitex_logging.getConsole``/``getLogger``, which carry the
    level, the aligned prefix and the searchable record the mandate exists
    for.
    """
    import scitex_logging as slogging

    slogging.getPlainConsole(__name__).emit(content, flush=False)


def render_rich(renderable, name: str, *, level: str = "info") -> None:
    """Render a Rich renderable through the SciTeX stdout console.

    Rich's ``Console.print`` is forbidden in shippable source (PS-220) and has
    no spare path: it always writes to a console stream that carries no level,
    no aligned prefix and no searchable record. So the renderable (a ``Table``,
    a markup string) is rendered with Rich's own renderer to text — the console
    stream is never written to — and that text is emitted as ONE levelled
    record. The table a reader sees is byte-identical; the operator gains the
    level.

    Parameters
    ----------
    renderable : Any
        Any Rich renderable: ``rich.table.Table``, markup ``str``, …
    name : str
        Logger name — pass ``__name__`` from the call site.
    level : str
        One of ``info``/``warning``/``error``/``success``.
    """
    import scitex_logging as slogging
    from rich.console import Console

    console = Console()
    lines = console.render_lines(renderable, console.options, pad=False)
    text = "\n".join("".join(segment.text for segment in line) for line in lines)
    getattr(slogging.getConsole(name), level)(text.rstrip("\n"))


def write_stream(text: str, stream: TextIO, *, flush: bool = False) -> None:
    """Write one already-rendered line verbatim to a caller-owned stream.

    Parameters
    ----------
    text : str
        The already-rendered line. Passed through unchanged — no level prefix
        is added, because the caller owns both the payload and the stream.
    stream : TextIO
        The caller-supplied destination. Required, so the destination is never
        chosen here.
    flush : bool
        Flush after writing. Used by the one-shot startup diagnostics that
        must reach the operator before a slow import continues.

    Returns
    -------
    None
    """
    import scitex_logging as slogging

    slogging.getPlainConsole(__name__).emit(text, stream=stream, flush=flush)
