#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resolve authored SciTeX skill directories and delegate evaluation to newb.

The installed standalone newb package owns prompts, execution, rendering and
result semantics. Dev adds ecosystem distribution-to-checkout resolution.
Newb is a declared base dependency; lazy import avoids loading its runtime for
metadata/help inspection and a missing dependency is a broken installation.
The module-level render_markdown attribute remains a lazy compatibility export.
See general/05_development/04_skills-self-explain.md for acceptance boundaries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def _require_newb():
    """Import the declared base dependency or report a broken installation."""
    try:
        import newb as _newb
    except (
        ImportError
    ) as exc:  # pragma: no cover — tested with monkeypatched sys.modules
        raise SystemExit(
            "scitex-dev: `skills explain-self` requires `newb`, which is a "
            "BASE dependency — so this is a broken or partial install, not "
            "a missing extra. Reinstall into this interpreter:\n"
            "    python -m pip install --force-reinstall scitex-dev"
        ) from exc
    return _newb


def _newb_run_callable(_newb):
    """Prefer newb's test entrypoint when present, otherwise use run."""
    fn = getattr(_newb, "test", None)
    if fn is None:
        fn = getattr(_newb, "run", None)
    if fn is None:
        raise SystemExit(
            "scitex-dev: installed `newb` exposes neither `test` nor `run`; "
            "Repair the declared dependencies in this interpreter; "
            "there is no scitex-dev[skills] extra."
        )
    return fn


def __getattr__(name: str):
    """Lazy module-level ``render_markdown`` for back-compat callers.

    Older callers do ``from scitex_dev._cli.skills._self_explain import
    render_markdown``. We honour that, but only resolve newb at attribute
    access time so a bare scitex-dev install can still import this
    module.
    """
    if name == "render_markdown":
        return _require_newb().render_markdown
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _find_skills_dir(
    distribution: str,
    *,
    ecosystem: dict | None = None,
    local_path_lookup=None,
) -> Path:
    """Locate ``_skills/<distribution>/`` for a given ecosystem package.

    Resolution: ``<local_path>/src/<import_name>/_skills/<distribution>/``.

    ``ecosystem`` / ``local_path_lookup`` are test-injection hooks so
    callers can supply a synthetic registry without monkey-patching.
    """
    if ecosystem is None or local_path_lookup is None:
        from ..._ecosystem import ECOSYSTEM as _ECO, get_local_path as _gpl

        if ecosystem is None:
            ecosystem = _ECO
        if local_path_lookup is None:
            local_path_lookup = _gpl
    ECOSYSTEM = ecosystem
    get_local_path = local_path_lookup

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
    skills_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Have an agent (mounted with only this package's skills) self-explain.

    Resolve the ecosystem distribution's authored skills directory and pass
    it to the installed newb entrypoint. Result semantics belong to newb.

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
        The installed newb entrypoint's result, without normalizing or
        verifying its generated claims. Inspect that version's contract.
    """
    _newb = _require_newb()
    _newb_run = _newb_run_callable(_newb)
    if skills_dir is None:
        skills_dir = _find_skills_dir(distribution)
    return _newb_run(
        skills_dir,
        model=model,
        runs_per_prompt=runs_per_prompt,
        _runner=_runner,
    )


# EOF
