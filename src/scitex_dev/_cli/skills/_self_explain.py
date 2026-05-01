#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Have an agent (mounted with only one package's skills) self-explain it.

See ``general/05_development_04_skills-self-explain.md`` for concept,
canonical prompts, and cost considerations.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Canonical prompts -- exposed as module constants so they are greppable
# and overridable. Edit with care: these define the README's "what does
# this do?" answers across the whole ecosystem.
# ---------------------------------------------------------------------------

_PROMPT_WHAT_FOR = (
    "Read the skills under ~/.claude/skills/ and answer in ONE sentence: "
    "what is this package for?"
)

_PROMPT_PROBLEMS = (
    "Read the skills under ~/.claude/skills/ and list 3-5 problems this "
    "package solves. Output as a markdown table with columns: "
    "| # | Problem | Solution |. No prose around the table."
)

_PROMPT_QUICK_START = (
    "Read the skills under ~/.claude/skills/ and show the canonical Quick "
    "Start example as a Python code block. Just the code, no commentary."
)

_PROMPTS = {
    "what_for": _PROMPT_WHAT_FOR,
    "problems_solved": _PROMPT_PROBLEMS,
    "quick_start": _PROMPT_QUICK_START,
}


# ---------------------------------------------------------------------------
# Skill-tree resolution
# ---------------------------------------------------------------------------


def _find_skills_dir(distribution: str) -> Path:
    """Locate ``_skills/<distribution>/`` for a given ecosystem package.

    Resolution order:
      1. ``<local_path>/src/<import_name>/_skills/<distribution>/``
      2. raise FileNotFoundError with a helpful message.
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


def _stage_skills_mount(skills_src: Path, distribution: str) -> Path:
    """Build a temp dir shaped as ``<tmp>/.claude/skills/<dist>/``.

    The container expects to mount HOME, and ``claude`` looks at
    ``$HOME/.claude/skills/...``. We give it a clean HOME with ONLY this
    package's skills present.
    """
    tmp = Path(tempfile.mkdtemp(prefix=f"self-explain-{distribution}-"))
    target = tmp / ".claude" / "skills" / distribution
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skills_src, target)
    return tmp


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def self_explain(
    distribution: str,
    *,
    model: str = "claude-haiku-4-5",
    runs_per_prompt: int = 1,
    _runner: Optional[Any] = None,
) -> Dict[str, Any]:
    """Have an agent (mounted with only this package's skills) self-explain.

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
        ``{"package", "what_for", "problems_solved", "quick_start"}``.
        Values are strings when ``runs_per_prompt == 1``, lists otherwise.
    """
    skills_src = _find_skills_dir(distribution)

    runner = _runner
    cleanup_mount: Optional[Path] = None
    try:
        if runner is None:
            from ..._agentic_testing._core import NewbieDockerRunner

            mount = _stage_skills_mount(skills_src, distribution)
            cleanup_mount = mount
            runner = NewbieDockerRunner(skills_mount=mount)

        out: Dict[str, Any] = {"package": distribution}
        for key, prompt in _PROMPTS.items():
            answers = []
            for _ in range(max(1, int(runs_per_prompt))):
                result = runner.run(prompt, model=model)
                answers.append(_extract_text(result))
            out[key] = answers[0] if runs_per_prompt == 1 else answers
        return out
    finally:
        if cleanup_mount is not None and cleanup_mount.exists():
            shutil.rmtree(cleanup_mount, ignore_errors=True)
        if runner is not None and hasattr(runner, "close") and _runner is None:
            try:
                runner.close()
            except Exception:
                pass


def _extract_text(result: Any) -> str:
    """Pull the assistant's final text from a ``claude -p`` JSON envelope."""
    if isinstance(result, dict):
        r = result.get("result")
        if isinstance(r, str):
            return r
    if isinstance(result, str):
        return result
    return ""


# EOF
