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

# Tiered question set. Each tier has a clear purpose:
#   identity  — what is this and why does it exist (1 sentence + table)
#   usage     — show me the minimum thing that works (code)
#   boundary  — what is this NOT for (red test; agent must redirect, not hallucinate)
# Authors override the boundary tier per-package via
# ``src/<pkg>/_skills/<pkg>/_red_tests.yaml`` so each package gets its
# own targeted "no, that's not us" pairs.

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
    "Read the skills under ~/.claude/skills/ and show the minimal working "
    "example as a Python code block. Just the code, no commentary."
)

_PROMPT_WHEN_NOT_TO_USE = (
    "Read the skills under ~/.claude/skills/ and answer in 1-2 sentences: "
    "when should someone NOT use this package? If the skills don't say, "
    "answer 'not specified in the skills'."
)

_PROMPTS_DEFAULT = {
    # Tier 1 — identity
    "what_for": _PROMPT_WHAT_FOR,
    "problems_solved": _PROMPT_PROBLEMS,
    # Tier 2 — usage
    "quick_start": _PROMPT_QUICK_START,
    "when_not_to_use": _PROMPT_WHEN_NOT_TO_USE,
}

# Backward-compat alias for callers / tests that grab _PROMPTS directly.
_PROMPTS = _PROMPTS_DEFAULT


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


def _load_red_tests(skills_src: Path) -> list[dict]:
    """Load per-package red tests from ``<skills_src>/_red_tests.yaml``.

    Schema (list of dicts):
        - question: "Can this do <unrelated thing>?"
          expect_contains: ["No", "scitex-X"]   # substrings the answer MUST contain
          expect_excludes: ["yes", "you can"]   # substrings the answer must NOT contain

    Missing file or invalid YAML → returns []. Authors are not required
    to provide red tests; the absence just skips the boundary tier.
    """
    red_file = skills_src / "_red_tests.yaml"
    if not red_file.is_file():
        return []
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return []
    try:
        data = yaml.safe_load(red_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for entry in data:
        if not isinstance(entry, dict) or "question" not in entry:
            continue
        out.append(
            {
                "question": str(entry["question"]),
                "expect_contains": list(entry.get("expect_contains") or []),
                "expect_excludes": list(entry.get("expect_excludes") or []),
            }
        )
    return out


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

        # Tier 4 — boundary / red tests. Author-provided per-package via
        # _red_tests.yaml; each entry asks a "can this do X?" question and
        # we score the answer against expect_contains / expect_excludes.
        red_results = []
        for entry in _load_red_tests(skills_src):
            ans_text = _extract_text(runner.run(entry["question"], model=model))
            low = ans_text.lower()
            passes_contains = all(s.lower() in low for s in entry["expect_contains"])
            passes_excludes = all(
                s.lower() not in low for s in entry["expect_excludes"]
            )
            red_results.append(
                {
                    "question": entry["question"],
                    "answer": ans_text,
                    "passed": bool(passes_contains and passes_excludes),
                }
            )
        if red_results:
            out["red_tests"] = red_results
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
