#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG rasterization for the icon generator (optional Pillow dependency).

Draws directly with Pillow (mirrors the reference PIL-based fleet
script's approach) rather than rasterizing the SVG output -- that would
need a second heavy dependency (an SVG-to-PNG renderer) just to produce
a raster image.

Lazy-imported from ``scitex_dev._icons.__init__``: ``pip install
scitex-dev[icons]`` pulls in Pillow; callers that only need
``generate_svg`` (pure stdlib) never pay that cost (PS-213
LAZY-EXTRA-PATTERN-OK).

Font choice matters for determinism: unlike the reference script (which
searches a list of *system* font paths -- fine for a one-off run on one
machine, but not reproducible across hosts where different fonts happen
to be installed), this module defaults to Pillow's own bundled bitmap
font (``ImageFont.load_default``), which ships inside the ``Pillow``
wheel itself and is therefore identical on every machine running the
same Pillow version. Pass ``font_path`` explicitly to opt into a
system/vendored TrueType font instead.
"""

from __future__ import annotations

import io

from ._colors import resolve_color
from ._label import derive_label, label_font_size

DEFAULT_SIZE = 512
WORDMARK = "SciTeX"


def _require_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - exercised via extras test
        raise ImportError(
            "generate_png() requires Pillow. Install with "
            "`pip install scitex-dev[icons]`."
        ) from exc
    return Image, ImageDraw, ImageFont


def _load_font(image_font_module, font_path: str | None, px_size: int):
    """Return a Pillow font object for ``px_size``.

    ``font_path`` given -> ``ImageFont.truetype(font_path, px_size)``
    (caller opts out of the deterministic default).
    Otherwise -> Pillow's bundled default bitmap font, scaled via the
    ``size=`` kwarg on Pillow >= 9.2; older Pillow silently falls back
    to the font's fixed native size (still deterministic, just not
    proportional to ``px_size``).
    """
    if font_path:
        return image_font_module.truetype(font_path, px_size)
    try:
        return image_font_module.load_default(size=px_size)
    except TypeError:  # pragma: no cover - old Pillow without size kwarg
        return image_font_module.load_default()


def generate_png(
    name: str,
    *,
    size: int = DEFAULT_SIZE,
    label: str | None = None,
    color: str | None = None,
    wordmark: str | None = WORDMARK,
    font_path: str | None = None,
) -> bytes:
    """Render a deterministic square PNG icon for ``name`` as raw bytes.

    Same visual scheme as :func:`scitex_dev._icons.generate_svg`:
    solid brand-color square + short white label + optional wordmark.

    Args:
        name: input string; drives the derived label + resolved color
            unless overridden below.
        size: square image size in pixels.
        label: explicit short label; overrides the name-derived one.
        color: explicit hex fill; overrides the resolved brand color.
        wordmark: small caption near the bottom; pass ``None`` to omit.
        font_path: explicit TrueType font path. Omit to use Pillow's
            bundled default font (see module docstring for why that is
            the deterministic default).

    Returns:
        Raw PNG bytes (RGB, no alpha, no metadata chunks).

    Raises:
        ImportError: if Pillow is not installed.

    Determinism: same inputs + same Pillow version -> byte-identical
    PNG output (no randomness, no timestamp/EXIF metadata is written).
    """
    Image, ImageDraw, ImageFont = _require_pillow()

    resolved_label = (label if label is not None else derive_label(name)).upper()
    fill = color or resolve_color(name)

    img = Image.new("RGB", (size, size), fill)
    draw = ImageDraw.Draw(img)

    label_px = max(int(label_font_size(resolved_label, size)), 1)
    label_font = _load_font(ImageFont, font_path, label_px)
    bbox = draw.textbbox((0, 0), resolved_label, font=label_font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - w) / 2 - bbox[0], size * 0.46 - h / 2 - bbox[1]),
        resolved_label,
        font=label_font,
        fill="white",
    )

    if wordmark:
        wm_px = max(int(size * 0.11), 1)
        wm_font = _load_font(ImageFont, font_path, wm_px)
        bbox = draw.textbbox((0, 0), wordmark, font=wm_font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((size - w) / 2 - bbox[0], size * 0.72 - h / 2 - bbox[1]),
            wordmark,
            font=wm_font,
            fill="white",
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
