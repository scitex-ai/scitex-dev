#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The ``cleanup:`` config block — DEFAULT OFF, and FAIL CLOSED.

Schema, in the per-repo ``<repo>/.scitex/dev/config.yaml``::

    cleanup:
      branches:
        enabled: true          # ABSENT / not literal YAML true => OFF
        min-age-days: 30       # clamped UP to HARD_MIN_AGE_DAYS; never down
        protect:               # extra never-touch globs, ADDITIVE
          - "relocation/*"

Keyed by sweep name (``branches``) so ``cleanup.worktrees`` /
``cleanup.bundles`` can be added later without a schema break, each
defaulting OFF independently.

TWO SURFACES, ``AND``-COMBINED
------------------------------
The PER-REPO file is the authority: deletion is a per-repo act and a
repo's own config travels with it and is reviewable in its git history.
The USER-SCOPE ``~/.scitex/dev/config.yaml`` is a fleet-wide KILL SWITCH.
**Both must say true.** Not either — both. With neither file present (the
state of every machine today) the sweep is OFF everywhere, which is the
correct default for a primitive whose failure mode is destroying work.

WHY THIS FAILS CLOSED WHEN ``gate/_config.py`` FAILS OPEN
---------------------------------------------------------
That module documents its fail-OPEN choice plainly, and it is right for
what it guards: a gate that hard-blocks on an unreadable config wedges
the whole repo, so the safe degradation there is "advisory". Here the
polarity inverts. A DELETER that fails open on an unreadable config
destroys work. So: missing file, unreadable file, malformed YAML,
``cleanup`` not a mapping, PyYAML absent — every one of them yields
``CleanupConfig(enabled=False)`` carrying the reason in ``error``.

The enabled test is ``raw.get("enabled") is True`` — IDENTITY against the
bool, so the string ``"true"``, the string ``"yes"`` and the integer ``1``
all read as OFF. A typo must never arm a deleter.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._branch_gc_model import DEFAULT_MIN_AGE_DAYS, clamp_min_age_days

__all__ = [
    "CONFIG_REL_PATH",
    "USER_CONFIG_REL_PATH",
    "CleanupConfig",
    "load_branch_cleanup_config",
]

CONFIG_REL_PATH = Path(".scitex") / "dev" / "config.yaml"
USER_CONFIG_REL_PATH = Path(".scitex") / "dev" / "config.yaml"

_SWEEP = "branches"


@dataclass(frozen=True)
class CleanupConfig:
    """Resolved ``cleanup.branches`` config for ONE repo.

    ``enabled`` defaults to ``False`` at the dataclass level — gate #1 of
    the four. Constructing this object with no arguments at all yields a
    config that deletes nothing.
    """

    enabled: bool = False
    min_age_days: float = DEFAULT_MIN_AGE_DAYS
    protect: tuple[str, ...] = ()
    repo_source: str | None = None
    user_source: str | None = None
    #: Why the sweep is OFF, when it is off for a reason other than "the
    #: operator did not turn it on". Never collapsed into ``enabled``.
    error: str | None = None

    @property
    def source(self) -> str | None:
        return self.repo_source


def _read_cleanup_block(path: Path, sweep: str) -> tuple[dict | None, str | None]:
    """Return ``(block, error)`` for ``cleanup.<sweep>`` in ``path``.

    ``block is None`` always means OFF. ``error`` is None only when the
    file was read, parsed, and simply did not opt in — every other route
    to None carries a stated reason.
    """
    if not path.is_file():
        return None, f"no config at {path}"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"unreadable config {path}: {exc}"
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        # No minimal-parser fallback here, deliberately: the audit loader
        # has one, and a subset parser guessing at a deleter's arming flag
        # is exactly the wrong place to be approximate.
        return None, "PyYAML not installed; refusing to arm branch cleanup"
    try:
        data = yaml.safe_load(text) or {}
    except Exception as exc:  # noqa: BLE001 - any parse failure means OFF
        return None, f"malformed YAML in {path}: {exc}"
    if not isinstance(data, dict):
        return None, f"top level of {path} is not a mapping"
    cleanup = data.get("cleanup")
    if cleanup is None:
        return None, None
    if not isinstance(cleanup, dict):
        return None, f"`cleanup` in {path} is not a mapping"
    block = cleanup.get(sweep)
    if block is None:
        return None, None
    if not isinstance(block, dict):
        return None, f"`cleanup.{sweep}` in {path} is not a mapping"
    return block, None


def _opted_in(block: dict | None) -> bool:
    """``enabled`` is armed ONLY by the literal YAML boolean ``true``."""
    if not block:
        return False
    return block.get("enabled") is True


def _protect_globs(block: dict | None) -> tuple[str, ...]:
    if not block:
        return ()
    raw = block.get("protect")
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, (list, tuple)):
        return tuple(str(entry) for entry in raw if str(entry).strip())
    return ()


def load_branch_cleanup_config(
    repo: str | Path,
    *,
    home: str | Path | None = None,
    sweep: str = _SWEEP,
) -> CleanupConfig:
    """Resolve ``cleanup.<sweep>`` for ``repo``. OFF unless BOTH files say true.

    ``home`` overrides where the fleet-wide kill switch is looked for
    (``<home>/.scitex/dev/config.yaml``); it exists so tests never read the
    invoking operator's real config, which would make the DEFAULT-OFF
    tests depend on the machine they run on.
    """
    repo_path = Path(repo)
    home_path = Path(home) if home is not None else Path.home()

    repo_cfg = repo_path / CONFIG_REL_PATH
    user_cfg = home_path / USER_CONFIG_REL_PATH

    repo_block, repo_err = _read_cleanup_block(repo_cfg, sweep)
    user_block, user_err = _read_cleanup_block(user_cfg, sweep)

    repo_on = _opted_in(repo_block)
    user_on = _opted_in(user_block)

    if repo_on and user_on:
        merged = repo_block or {}
        raw_age = merged.get("min-age-days", merged.get("min_age_days"))
        return CleanupConfig(
            enabled=True,
            min_age_days=clamp_min_age_days(raw_age),
            protect=_protect_globs(merged),
            repo_source=str(repo_cfg),
            user_source=str(user_cfg),
        )

    # OFF. Say WHY, in the order an operator would debug it: a real read
    # failure outranks a plain "not opted in", because the second is the
    # expected steady state and the first is a problem.
    reasons = [err for err in (repo_err, user_err) if err]
    if not reasons:
        reasons.append(
            f"`cleanup.{sweep}.enabled` is not literally true in "
            + ("the user config" if repo_on else str(repo_cfg))
        )
    return CleanupConfig(
        enabled=False,
        min_age_days=clamp_min_age_days(
            (repo_block or {}).get("min-age-days") if repo_block else None
        ),
        protect=_protect_globs(repo_block),
        repo_source=str(repo_cfg) if repo_cfg.is_file() else None,
        user_source=str(user_cfg) if user_cfg.is_file() else None,
        error="; ".join(reasons),
    )


# EOF
