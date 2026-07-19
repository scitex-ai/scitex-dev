"""Tests for ``scitex-dev cron install`` — the migration-safety surface.

Existing installed crontabs point at the pre-2026-07-19 lines (inline
mkdir + redirect + rotation). These tests pin the two properties that
make rewriting them safe: the operator can SEE the change before it is
applied, and lines that are not scitex-dev's own are never touched.
"""

from __future__ import annotations

from scitex_dev._cli.cron import _crontab, _jobs
from scitex_dev._cli.cron.install import _crontab_diff

# A realistic host crontab: the operator's own line, one OLD-style
# scitex-dev line, and another agent's line.
_FOREIGN_OWN = "0 3 * * * /home/me/backup.sh # not scitex"
_FOREIGN_SAC = "*/5 * * * * sac agents heartbeat # sac managed"
_OLD_STYLE = (
    "*/10 * * * * mkdir -p $HOME/.scitex/dev/logs && scitex-dev cron exec "
    "ci-watch >> $HOME/.scitex/dev/logs/cron-ci-watch.log 2>&1 "
    "# scitex-dev cron: ci-watch"
)
_HOST_CRONTAB = "\n".join(["# my own cron", _FOREIGN_OWN, _OLD_STYLE, _FOREIGN_SAC]) + "\n"


def _install_all(text: str) -> str:
    """Apply every registered job to ``text``, as `install --all` does."""
    for spec in _jobs.list_jobs():
        text = _crontab.upsert_managed(text, spec.name, spec.schedule, spec.command)
    return text


# -- the managed rewrite ----------------------------------------------------


def test_install_replaces_the_old_style_line():
    # Arrange
    # Act
    new = _install_all(_HOST_CRONTAB)
    # Assert — the dirty inline-plumbing line must not survive.
    assert _OLD_STYLE not in new


def test_install_writes_the_clean_replacement_line():
    # Arrange
    # Act
    new = _install_all(_HOST_CRONTAB)
    # Assert
    assert (
        "*/10 * * * * scitex-dev cron exec ci-watch # scitex-dev cron: ci-watch"
        in new
    )


def test_install_does_not_duplicate_an_already_managed_job():
    # Arrange
    # Act — idempotency: applying twice must be a fixed point.
    once = _install_all(_HOST_CRONTAB)
    twice = _install_all(once)
    # Assert
    assert once == twice


def test_install_emits_one_line_per_registered_job():
    # Arrange
    # Act
    new = _install_all(_HOST_CRONTAB)
    # Assert
    assert len(_crontab.parse_managed(new)) == len(_jobs.JOB_REGISTRY)


# -- foreign lines are sacred ----------------------------------------------


def test_install_preserves_the_operators_own_line():
    # Arrange
    # Act
    new = _install_all(_HOST_CRONTAB)
    # Assert — the host crontab also carries sac, lead and other agents'
    # jobs; every one of them must stay byte-identical.
    assert _FOREIGN_OWN in new


def test_install_preserves_another_agents_line():
    # Arrange
    # Act
    new = _install_all(_HOST_CRONTAB)
    # Assert
    assert _FOREIGN_SAC in new


def test_install_preserves_plain_comments():
    # Arrange
    # Act
    new = _install_all(_HOST_CRONTAB)
    # Assert
    assert "# my own cron" in new


def test_install_touches_no_line_lacking_the_scitex_marker():
    # Arrange
    foreign_before = [
        ln
        for ln in _HOST_CRONTAB.splitlines()
        if _crontab.MARKER_PREFIX not in ln
    ]
    # Act
    foreign_after = [
        ln for ln in _install_all(_HOST_CRONTAB).splitlines()
        if _crontab.MARKER_PREFIX not in ln
    ]
    # Assert
    assert foreign_after == foreign_before


# -- the dry-run diff -------------------------------------------------------


def test_dry_run_diff_shows_the_old_line_being_removed():
    # Arrange
    new = _install_all(_HOST_CRONTAB)
    # Act
    diff = _crontab_diff(_HOST_CRONTAB, new)
    # Assert — the operator must see exactly what leaves the crontab.
    assert f"-{_OLD_STYLE}" in diff


def test_dry_run_diff_shows_the_new_line_being_added():
    # Arrange
    new = _install_all(_HOST_CRONTAB)
    # Act
    diff = _crontab_diff(_HOST_CRONTAB, new)
    # Assert
    assert "+*/10 * * * * scitex-dev cron exec ci-watch" in diff


def test_dry_run_diff_does_not_mark_foreign_lines_as_changed():
    # Arrange
    new = _install_all(_HOST_CRONTAB)
    # Act
    diff = _crontab_diff(_HOST_CRONTAB, new)
    changed = [
        ln
        for ln in diff.splitlines()
        if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))
    ]
    # Assert — no +/- line may belong to someone else's job.
    assert not any("sac agents heartbeat" in ln or "backup.sh" in ln for ln in changed)


def test_dry_run_diff_is_empty_when_nothing_would_change():
    # Arrange — an already-migrated crontab.
    current = _install_all(_HOST_CRONTAB)
    # Act
    diff = _crontab_diff(current, _install_all(current))
    # Assert — a no-op install must LOOK like a no-op.
    assert diff == ""
