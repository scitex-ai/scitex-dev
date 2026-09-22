# -*- coding: utf-8 -*-
"""The ADR-0012-retired `cron` surface — one definition, every consumer.

ADR-0012 (``docs/adr/0012-periodic-jobs-run-in-the-supervisor-cron-is-retired.md``):
periodic jobs run in the supervisor; ``scitex-dev cron`` is retired and
``ecosystem up`` converges the managed crontab block to EMPTY. The files
under ``src/<pkg>/_cli/cron/`` are therefore FROZEN pending removal: they
receive no forward-looking convention migrations, because any rename there
is a live-identity migration, not a tidy-up.

Two rules consult this module, for two different reasons rooted in the
same freeze:

* PS-227 (``_check_job_naming``): the cron slugs (``ci-watch``, …) are
  crontab tag identities (``# scitex-dev cron: <name>``), not systemd
  unit filenames and not ``discover_jobs()`` first-class declarations.
  The package-qualification rename is a UNIT MIGRATION — ``scitex_dev/
  jobs/__init__.py`` says so in its own docstring: the built-ins "keep
  their historical bare slugs for backward compatibility with the
  existing ``scitex-dev cron`` CLI; renaming them is a UNIT MIGRATION
  (stop-old → remove-old → install-new → verify-exactly-one), never an
  in-place edit". A repo PR cannot perform that cutover, so the rule
  exempts this surface. PS-226/228/229 still apply here.
* PS-145 (``_check_local_state``): the ``scholar-library-sync``
  orchestration references ``~/.scitex/scholar/library`` as rsync/ssh
  remote paths — host-level fleet sync run by the supervisor owner
  itself, not a leaf reading another leaf's internal state. The
  plugin-port remedy needs a cross-package contract change in scholar
  for a surface that is being deleted. Exempt until removal.

When ``_cli/cron/`` is deleted, this module and its two call sites go
with it — grep for ``is_retired_cron_surface`` to find every piece.
"""

from __future__ import annotations

from pathlib import Path

#: Path segments identifying the retired surface, relative to the repo
#: root. Structural (``_cli/cron`` consecutively), not package-named, so
#: the predicate survives renames of the owning package.
_RETIRED_CRON_SEGMENTS = ("_cli", "cron")


def is_retired_cron_surface(path: Path, repo: Path) -> bool:
    """True iff *path* lives under the ADR-0012-retired cron surface.

    *path* may be absolute or repo-relative; *repo* is the repository
    root. Anything outside *repo* (or unresolvable against it) returns
    False — the exemption never leaks onto files the audit did not mean
    to grade.
    """
    try:
        rel_parts = Path(path).relative_to(repo).parts
    except ValueError:
        return False
    return any(
        rel_parts[i] == _RETIRED_CRON_SEGMENTS[0]
        and rel_parts[i + 1] == _RETIRED_CRON_SEGMENTS[1]
        for i in range(len(rel_parts) - 1)
    )


__all__ = ["is_retired_cron_surface"]
