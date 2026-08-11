#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic name -> icon/avatar generator for the SciTeX ecosystem.

Common tooling: turns an arbitrary label (an agent id, a package name)
into a small square icon -- SVG (primary, pure stdlib) or PNG (raster,
needs Pillow) -- so any ecosystem consumer (scitex-todo's board, sac's
fleet views, eventually cct's bot avatars via a manual BotFather upload)
can generate a consistent avatar without hand-rolling PIL calls.

Style ported (as a starting point, not a dependency) from the one-off
``claude-code-telegrammer`` fleet avatar script
(``docs/icons/generate_bot_icons.py``, commit ``1973772``), consulted as
REFERENCE MATERIAL only: solid brand-color square + short white label +
an optional "SciTeX" wordmark. See ``_colors.py`` for the brand-color
map + deterministic hash fallback, ``_label.py`` for the default label
scheme.

Standing ecosystem convention (operator, non-negotiable): this module
has ZERO import-time or runtime dependency on ``scitex_agent_container``
(sac) or ``claude_code_telegrammer`` (cct) -- sac/cct/todo stay
independent; shared behavior between them is conventions/patterns
(docs), never shared code imports or co-locked interfaces. Downstream
packages import FROM here; this module imports from neither.

Public API::

    generate_svg(name, *, size=512, label=None, color=None,
                 wordmark="SciTeX") -> str
    generate_png(name, *, size=512, label=None, color=None,
                 wordmark="SciTeX", font_path=None) -> bytes
    save_icon(name, out_dir, *, size=512, label=None, color=None,
              wordmark="SciTeX", formats=("svg", "png"),
              stem=None) -> dict[str, Path]
    resolve_color(name) -> str
    derive_label(name, *, max_chars=3) -> str

Example::

    >>> from scitex_dev._icons import generate_svg, resolve_color
    >>> svg = generate_svg("scitex-todo")          # doctest: +SKIP
    >>> resolve_color("scitex-todo")
    '#2f9e9e'
    >>> from scitex_dev._icons import save_icon
    >>> save_icon("my-agent", "/tmp/icons")         # doctest: +SKIP
    {'svg': PosixPath('/tmp/icons/my-agent.svg'),
     'png': PosixPath('/tmp/icons/my-agent.png')}

``generate_png`` (and ``save_icon`` with ``"png"`` in ``formats``) needs
Pillow, which ships in the BASE install — the ``[icons]`` extra that
once gated it is gone (PS-225: extra names are restricted to
``{all, dev, docs}``). The import is still LAZY, so ``generate_svg``
alone does not pay Pillow's import cost; that is a startup-time
property now, not a dependency-set one.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._colors import KNOWN_COLORS, resolve_color
from ._label import derive_label
from ._svg import DEFAULT_SIZE, WORDMARK, generate_svg

__all__ = [
    "DEFAULT_SIZE",
    "WORDMARK",
    "KNOWN_COLORS",
    "resolve_color",
    "derive_label",
    "generate_svg",
    "generate_png",
    "save_icon",
]


def generate_png(name: str, **kwargs) -> bytes:
    """Render a deterministic square PNG icon for ``name`` as raw bytes.

    Thin lazy-import wrapper -- see
    :func:`scitex_dev._icons._png.generate_png` for the full signature
    and docs. Requires Pillow, which ships in the base install.
    """
    from ._png import generate_png as _generate_png

    return _generate_png(name, **kwargs)


def save_icon(
    name: str,
    out_dir: str | Path,
    *,
    size: int = DEFAULT_SIZE,
    label: str | None = None,
    color: str | None = None,
    wordmark: str | None = WORDMARK,
    formats: tuple[str, ...] = ("svg", "png"),
    stem: str | None = None,
    dry_run: bool = False,
) -> dict[str, Path]:
    """Render ``name``'s icon and write it to ``out_dir`` in ``formats``.

    Args:
        name: input string (agent id / package name / arbitrary label).
        out_dir: destination directory; created if missing.
        size, label, color, wordmark: forwarded to
            :func:`generate_svg` / :func:`generate_png`.
        formats: which output format(s) to write -- any subset of
            ``("svg", "png")``.
        stem: output filename stem (without extension); defaults to a
            filesystem-safe slug derived from ``name``.
        dry_run: when ``True``, compute the destination paths (same slug
            logic used for a real run) but skip creating ``out_dir`` and
            skip both the SVG/PNG rendering and the filesystem writes.
            Lets a caller (the CLI's ``--dry-run``) preview exactly what
            a real run would produce -- including which files would be
            overwritten -- with zero side effects, and without requiring
            Pillow just to preview a PNG path.

    Returns:
        A dict mapping each written format to its output ``Path``, e.g.
        ``{"svg": Path("out/my-agent.svg"), "png": Path("out/my-agent.png")}``.
        When ``dry_run`` is set, the paths are the ones that *would* be
        written -- nothing is created on disk.
    """
    out_dir = Path(out_dir)
    slug = stem or _slugify(name)

    written: dict[str, Path] = {}
    if "svg" in formats:
        svg_path = out_dir / f"{slug}.svg"
        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
            svg_path.write_text(
                generate_svg(
                    name, size=size, label=label, color=color, wordmark=wordmark
                )
            )
        written["svg"] = svg_path
    if "png" in formats:
        png_path = out_dir / f"{slug}.png"
        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
            png_path.write_bytes(
                generate_png(
                    name, size=size, label=label, color=color, wordmark=wordmark
                )
            )
        written["png"] = png_path
    return written


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "icon"
