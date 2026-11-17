"""PS-166 — README badge labels use the standardized short vocabulary.

Every SciTeX README's badge block (the canonical
``<!-- scitex-badges:start -->...<!-- scitex-badges:end -->`` region,
or any other shields.io badge in the README) MUST use one of the
standardized short labels so the ecosystem-wide README sweep can scan
badges as a uniform row:

    pypi, python, docs, tests, install-check, quality, cov

Reference implementation: scitex-agent-container README badge block.
Spec: ``_skills/general/02_package/12_workflows-naming.md``
(``§Standardized badge labels``).

Detection: scan README.md for ``img.shields.io/.../label=<LABEL>``
patterns. For each badge, the URL-encoded ``label=`` parameter must be
one of the allowed values. Common deviations we want to catch:

  - ``label=Tests``        → use ``tests``
  - ``label=PyPI``         → use ``pypi``
  - ``label=Coverage``     → use ``cov``
  - ``label=Documentation``→ use ``docs``
  - ``label=Quality``      → use ``quality`` (case)
  - shields default labels (no ``?label=``) on workflow badges

Severity W during adoption.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

# The standardized short vocabulary.
ALLOWED_LABELS = frozenset(
    {
        "pypi",
        "python",
        "docs",
        "tests",
        "install-check",
        "quality",
        "cov",
    }
)

# Match a shields.io URL with optional `?label=...` query parameter. The
# URL ends at whitespace, double-quote, single-quote, `<`, `>`, or `)`.
_SHIELDS_URL_RE = re.compile(
    r"https?://img\.shields\.io/[^\s\"'<>)]+",
    re.IGNORECASE,
)

# Shields routes whose default (auto-generated) label is non-standard and
# must be overridden via `?label=...`. These are the routes we use most.
# An unset label on these routes is itself a deviation.
_REQUIRES_EXPLICIT_LABEL = (
    re.compile(r"/github/actions/workflow/status/", re.IGNORECASE),
    re.compile(r"/pypi/v/", re.IGNORECASE),
    re.compile(r"/pypi/pyversions/", re.IGNORECASE),
    re.compile(r"/codecov/c/github/", re.IGNORECASE),
)


def _badge_urls_and_labels(text: str) -> Iterator[tuple[str, str | None]]:
    """Read the first nonempty label from real URL query parameters.

    HTML is decoded once, before query fields are split and percent-decoded.
    Encoded separators and fragment/value decoys cannot create extra fields.
    Shared by the label and row-layout auditors; unrelated links are excluded.
    """
    for match in _SHIELDS_URL_RE.finditer(text):
        url = unescape(match.group(0))
        parameters = parse_qsl(urlsplit(url).query, keep_blank_values=True)
        label = next(
            (value for name, value in parameters if name.lower() == "label" and value),
            None,
        )
        yield url, label


def _suggest(actual: str) -> str:
    """Suggest the canonical label for a known deviation."""
    a = actual.lower()
    mapping = {
        "test": "tests",
        "tests": "tests",
        "ci": "tests",
        "build": "tests",
        "pypi": "pypi",
        "pypi version": "pypi",
        "version": "pypi",
        "python versions": "python",
        "python version": "python",
        "python": "python",
        "py versions": "python",
        "documentation": "docs",
        "docs": "docs",
        "rtd": "docs",
        "read the docs": "docs",
        "coverage": "cov",
        "codecov": "cov",
        "cov": "cov",
        "quality": "quality",
        "audit": "quality",
        "install": "install-check",
        "install check": "install-check",
        "install-check": "install-check",
        "smoke": "install-check",
        "import smoke": "install-check",
    }
    return mapping.get(a, "")


def check_ps166_readme_badge_labels(
    repo: Path, violation_cls: type, out: list[Any]
) -> None:
    """PS-166 — README badge labels match the standardized vocabulary."""
    readme = repo / "README.md"
    if not readme.is_file():
        return
    try:
        text = readme.read_text(errors="ignore")
    except OSError:
        return

    seen: set[tuple[str, str]] = set()  # de-dup (badge_url, reason)

    for url, raw in _badge_urls_and_labels(text):
        if raw is None:
            # Only flag missing labels on routes whose auto-generated label
            # is non-standard. Static badges (e.g. /badge/foo-bar-blue) are
            # exempt.
            if any(p.search(url) for p in _REQUIRES_EXPLICIT_LABEL):
                key = (url, "missing")
                if key not in seen:
                    seen.add(key)
                    out.append(
                        violation_cls(
                            "PS-166",
                            str(readme),
                            (
                                f"shields.io badge has no `?label=...` override "
                                f"({url[:80]}…). Add `?label=<one of "
                                f"{sorted(ALLOWED_LABELS)}>` so the README badge "
                                f"row is uniform across the ecosystem. See "
                                f"_skills/general/02_package/12_workflows-naming.md "
                                f"§Standardized badge labels."
                            ),
                        )
                    )
            continue

        if raw in ALLOWED_LABELS:
            continue

        suggestion = _suggest(raw)
        hint = f" (use `{suggestion}`)" if suggestion else ""
        key = (url, raw)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            violation_cls(
                "PS-166",
                str(readme),
                (
                    f"shields.io badge uses non-standard label "
                    f"`label={raw}`{hint} — allowed labels are "
                    f"{sorted(ALLOWED_LABELS)}. See "
                    f"_skills/general/02_package/12_workflows-naming.md "
                    f"§Standardized badge labels."
                ),
            )
        )
