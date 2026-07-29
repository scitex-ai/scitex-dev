"""Version resolution for the root CLI — THREE-valued, not two.

Extracted from ``_root.py`` to keep that file under the 512-line limit,
following the same convention as ``_root_help.py``.

Resolving a version has three outcomes, and collapsing them to two is how
a CLI reports a confident number nobody can rely on:

* **resolved** — exactly one installed ``*.dist-info``. Return it.
* **absent** — none of them (a source checkout, a ``PYTHONPATH`` import).
  A legitimate state, and NOT an error; say so rather than invent a number.
* **AMBIGUOUS** — two or more claim the name. ``importlib.metadata`` picks
  one by an order the spec leaves UNSPECIFIED, and the one it picks need
  not describe the module tree that actually imports.

The third value is not hypothetical
-----------------------------------
Measured in this project's own container, 2026-07-30::

    scitex_dev-0.38.0.dist-info
    scitex_dev-0.38.1.dist-info
    importlib.metadata.version("scitex-dev")  ->  0.38.0   (the OLDER)
    scitex-dev --version                      ->  "scitex-dev 0.38.0"

printed with no marker that a choice had been made, while PyPI was at
0.40.4. Two probes were run the same minute: a bare ``import scitex_dev``
said nothing, and ``--version`` said nothing — the CLI *does* mount an
integrity self-check, but not on the path to the version string, so the one
command a human runs to ask "what am I running" answered with one of two
arbitrary values.

``_release/dist_info_integrity`` had already DETECTED this condition and
documented it in detail, including that the resolution went to the older
dist-info. Nothing consulted it on the way to the user. Detection without
a consumer is the same as no detection.

Why this reports the number AND the doubt, rather than withholding it
---------------------------------------------------------------------
Suppressing the version under ambiguity would be worse than printing it:
callers parse this string, and a missing version reads as a BROKEN install
rather than an AMBIGUOUS one — trading a wrong answer for a different wrong
answer. So the resolved value is kept and the ambiguity is stated beside
it. A check that cannot determine something must not emit what a check
that determined it emits; it may still emit what it *did* find, labelled.

Same shape as ``UNPARSED`` in the diff extractor and ``UNREADABLE`` in the
masking summary — the third value has to be representable or it silently
becomes the second.
"""

from __future__ import annotations

__all__ = ["resolve_version", "AMBIGUOUS_MARKER"]

#: Substring callers (and tests) can key on to detect the ambiguous case
#: without parsing the whole sentence.
AMBIGUOUS_MARKER = "AMBIGUOUS"

_UNKNOWN = "0.0.0-unknown"


def resolve_version(
    distribution: str = "scitex-dev",
    site_packages=None,
) -> str:
    """Return a version string, or one that says why it can't be trusted.

    ``site_packages`` is passed through to ``count_dist_infos`` as its
    real-directory test seam — point it at a tmp dir seeded with actual
    ``.dist-info`` directories. No mocks: the ambiguous branch must be
    provable against real dirs, because testing it against a container's
    ACCIDENTAL duplication would pass for the wrong reason and vanish the
    moment someone reinstalls.
    """
    try:
        from importlib.metadata import version

        resolved: str | None = version(distribution)
    except Exception:  # noqa: BLE001 — absent is a legitimate state
        resolved = None

    try:
        from scitex_dev._release.dist_info_integrity import count_dist_infos

        n_claims = count_dist_infos(distribution, site_packages=site_packages)
    except Exception:  # noqa: BLE001 — never break `--version` over this
        # Fall back to whatever metadata said. This is a DEGRADED path, not
        # a clean one: it cannot see ambiguity, so it must not be reached
        # by anything that treats a plain string as proof of a clean install.
        return resolved if resolved is not None else _UNKNOWN

    if n_claims > 1:
        shown = resolved if resolved is not None else "unknown"
        return (
            f"{shown} ({AMBIGUOUS_MARKER}: {n_claims} dist-info directories "
            f"claim {distribution}; resolution among duplicates is "
            f"unspecified, so this may not describe the code that imports "
            f"— reinstall to collapse them)"
        )
    return resolved if resolved is not None else _UNKNOWN


# EOF
