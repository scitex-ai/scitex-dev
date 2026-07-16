#!/usr/bin/env python3
"""The audit must never substitute a *different* tree for the one asked about.

`_resolve_repo_root` used to GUESS when the package lived in site-packages: it
tried ``~/proj/<dist>``, then scanned every directory under ``/home`` for
``<user>/proj/<dist>``, and returned whichever matched first — with two bare
``except Exception: pass`` around the scans.

On 2026-07-14 that produced a CI verdict about the wrong code. PR #691 in
scitex-agent-container changed exactly one thing: it renamed a test file. Its
CI reported a PS-204 violation AT THE OLD NAME, under
``/data/gpfs/.../scitex-agent-container``. A tree cannot hold the new name and
report the old one — the auditor was never reading the PR. On the runner,
``~/proj/<name>`` is a symlink into the shared GPFS checkout. The gate failed a
clean PR, and would equally have passed a dirty one.

A resolver that answers with the WRONG tree is worse than one that answers "I
don't know", because the caller cannot tell the difference.

These tests use the real filesystem and no fixtures that rewrite production
internals. The first one FAILS on the guessing implementation.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from scitex_dev._cli.audit._project import _discovery
from scitex_dev._cli.audit._project._discovery import _resolve_repo_root


def test_resolver_never_reads_other_users_home_directories() -> None:
    # Arrange: the resolver's own source is the artifact under test — a guessing
    # branch cannot be observed from CI, where no ``/home/*/proj`` exists to be
    # guessed into. That CI-blindness is exactly why the bug survived, so the
    # assertion is made against the code rather than a mocked environment.
    source = inspect.getsource(_discovery._resolve_repo_root)

    # Act
    scans_home = 'Path("/home")' in source or "Path('/home')" in source
    guesses_home_proj = (
        'Path.home() / "proj"' in source or "Path.home() / 'proj'" in source
    )

    # Assert
    assert not scans_home and not guesses_home_proj, (
        "_resolve_repo_root must not GUESS a checkout by scanning /home or "
        "expanding ~/proj. `~` expands to WHOEVER IS ASKING; the code under "
        "audit is at the path the CALLER named. Substituting one for the other "
        "silently audits a different tree — it fails clean PRs and passes dirty "
        "ones. If the repo cannot be located from the package itself, return "
        "None and let the caller fail loudly or pass --path."
    )


def test_unlocatable_package_resolves_to_none_not_to_a_lookalike_checkout(
    tmp_path: Path,
) -> None:
    # Arrange: a real, plausible-looking decoy checkout — the exact shape the old
    # code would have returned. Real directories, real bytes on disk.
    decoy = tmp_path / "proj" / "scitex-does-not-exist-anywhere"
    decoy.mkdir(parents=True)
    (decoy / "pyproject.toml").write_text("[project]\nname = 'decoy'\n")

    # Act: the distribution is not importable at all, so there is nothing to walk
    # up from — the only way to return a path is to invent one.
    resolved = _resolve_repo_root("scitex-does-not-exist-anywhere", None)

    # Assert
    assert resolved is None, (
        f"resolver invented a tree ({resolved}) for a package it cannot locate"
    )


def test_explicit_repo_is_still_honoured(tmp_path: Path) -> None:
    # Arrange: passing the path explicitly (--path) is the supported way to name
    # the tree under audit, and it must keep working.
    repo = tmp_path / "workspace" / "scitex-agent-container"
    repo.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname = 'real'\n")

    # Act
    resolved = _resolve_repo_root("scitex-agent-container", repo)

    # Assert
    assert resolved == repo.resolve()
