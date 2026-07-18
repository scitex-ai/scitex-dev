#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/_editable.py

"""The editable-install content probe — built AROUND the check we already own.

THE WHOLE POINT OF THIS MODULE (non-negotiable #2)
--------------------------------------------------
For a WHEEL install, ``importlib.metadata.version()`` is trustworthy: the
metadata shipped in the same ``.dist-info`` as the code, so comparing it to
PyPI answers "am I behind?" honestly.

For an EDITABLE install it is a TRAP. The metadata is an install-time
SNAPSHOT frozen at ``pip install -e`` and the code moves on freely
afterwards. A developer's editable checkout routinely reports, say, 0.21.21
in its frozen ``.dist-info`` while ``develop`` is on 0.31.1 — and sac's
``check_host_behind_pypi`` would then fire a FALSE STALE and, worse, hand
out the remedy ``pip install -U <dist>==0.31.1``, which would CLOBBER the
editable checkout with a wheel. That check is deliberately NOT applied to
editable installs. Instead we ask the CONTENT: is the working tree behind
its own latest release tag?

That content probe already exists in this package as
``scitex_dev._release.check_editable_drift`` (PEP 610 direct_url.json ->
editable detect; working-tree HEAD vs latest ``v*`` tag; ahead-only is not
stale). We do NOT rewrite it — we reuse its git and detection helpers, and
lift its ahead/behind facts into the tri-state
:class:`~scitex_dev.versioning._model.Finding` the primitive speaks.
"""

from __future__ import annotations

from pathlib import Path

# Reuse — do not rewrite — the correct content-probe we already own.
from .._release.check_editable_drift import (
    _editable_source_dir as _detect_editable_source_dir,
)
from .._release.check_editable_drift import (
    _run_git,
)

__all__ = ["editable_ahead_behind", "editable_source_dir"]


def editable_source_dir(distribution: str) -> Path | None:
    """The editable-install source directory, or ``None`` if not editable.

    Thin pass-through to :func:`check_editable_drift._editable_source_dir`
    (PEP 610 ``direct_url.json``). Named without the leading underscore so
    this package has a stable seam onto the detection it depends on.
    """
    return _detect_editable_source_dir(distribution)


def editable_ahead_behind(repo: Path) -> tuple[int, int] | None:
    """``(ahead, behind)`` commits of the working tree vs its latest ``v*`` tag.

    ``None`` (=> UNKNOWN) when the checkout, git, or a release tag cannot be
    resolved — a source that cannot see says so, it does not report "0
    behind" and pretend it looked.

    The tag is chosen by highest semver (``--sort=-v:refname``), NOT
    ``git describe`` (which only finds tags reachable from HEAD and so
    breaks the standard gitflow case of ``v*`` tags living on ``main``
    while the developer is on ``develop``). This mirrors
    ``check_editable_drift._compute_drift`` exactly, by design.
    """
    raw = _run_git(repo, "tag", "--list", "v[0-9]*", "--sort=-v:refname")
    latest_tag = raw.splitlines()[0].strip() if raw else ""
    head = _run_git(repo, "rev-parse", "--short", "HEAD")
    if not latest_tag or not head:
        return None
    ahead = _run_git(repo, "rev-list", "--count", f"{latest_tag}..HEAD")
    behind = _run_git(repo, "rev-list", "--count", f"HEAD..{latest_tag}")
    try:
        return (int(ahead or "0"), int(behind or "0"))
    except ValueError:
        return None


# EOF
