#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex-dev wrapper around ``newb.self_explain``.

The implementation lives upstream in the standalone ``newb`` package
(https://pypi.org/project/newb/). scitex-dev's value-add is just the
ecosystem-aware distribution-name → ``_skills/<dist>/`` resolver.

See ``general/05_development_04_skills-self-explain.md`` for the concept.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from newb import render_markdown as _newb_render_markdown
from newb import test as _newb_run  # noqa: F401  (used by self_explain below)

# Re-export so existing callers (``_cli/skills/_manage.py``) keep working.
render_markdown = _newb_render_markdown


def _find_skills_dir(distribution: str) -> Path:
    """Locate ``_skills/<distribution>/`` for a given ecosystem package.

    Resolution: ``<local_path>/src/<import_name>/_skills/<distribution>/``.
    """
    from ..._ecosystem import ECOSYSTEM, get_local_path

    if distribution not in ECOSYSTEM:
        raise ValueError(
            f"Unknown distribution {distribution!r}. Known: {sorted(ECOSYSTEM)[:5]}..."
        )
    local = get_local_path(distribution)
    import_name = ECOSYSTEM[distribution]["import_name"]
    if local is None:
        raise FileNotFoundError(
            f"No local checkout for {distribution!r} "
            f"(ecosystem entry has no local_path)."
        )
    candidate = local / "src" / import_name / "_skills" / distribution
    if not candidate.is_dir():
        raise FileNotFoundError(
            f"Expected skills dir not found: {candidate}. "
            f"Has the package been laid out with _skills/<dist>/ yet?"
        )
    return candidate


def self_explain(
    distribution: str,
    *,
    model: str = "claude-haiku-4-5",
    runs_per_prompt: int = 1,
    _runner: Optional[Any] = None,
) -> Dict[str, Any]:
    """Have an agent (mounted with only this package's skills) self-explain.

    Thin wrapper: resolves a SciTeX ecosystem distribution name to its
    ``_skills/<dist>/`` directory and delegates to :func:`newb.self_explain`.

    Parameters
    ----------
    distribution
        Ecosystem distribution name, e.g. ``"scitex-io"``.
    model
        Claude model id passed to ``claude -p --model``.
    runs_per_prompt
        How many times to ask each prompt. >1 returns lists; ==1 returns
        scalars (the common case).
    _runner
        Test seam — inject a runner with a ``.run(prompt, model=...)``
        method to bypass docker.

    Returns
    -------
    dict
        ``{"package", "what_for", "problems_solved", "quick_start",
        "when_not_to_use"[, "red_tests"]}``. The ``"package"`` field is
        populated from ``skills_dir.name``, which is the distribution
        name in the SciTeX layout (``_skills/<dist>/``).
    """
    skills_dir = _find_skills_dir(distribution)
    return _newb_run(
        skills_dir,
        model=model,
        runs_per_prompt=runs_per_prompt,
        _runner=_runner,
    )


# EOF
