#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Host-capability probe + pre-existing-supervisor scan for the kind groups.

Shared by ``ecosystem dev service`` and ``ecosystem dev timer``. Both are
systemd-backed, and systemd ``--user`` IS NOT UNIVERSALLY AVAILABLE — that
is measured, not defensive:

===================  =====================================================
host                 ``systemd --user``
===================  =====================================================
ywata-note-win       available (state ``degraded``, 6 failed units)
mba                  **absent — macOS/launchd**, a different mechanism
scitex-compute-01..04 running (``/run/user/1000/systemd``)
scitex-nas-01        **absent — ``systemctl: command not found``** (Synology,
                     armv7l, Linux 4.2.8)
scitex-nas-02        **absent — ``systemctl: command not found``** (QNAP)
scitex-nas-03        running (``/run/user/1001/systemd``)
===================  =====================================================

Three of nine hosts cannot run a ``kind="service"`` or ``kind="timer"``
job AT ALL. ``kind="cron"`` is the only mechanism that works everywhere
(nas-01/-02 ship a working ``crontab`` binary), so a package that needs a
periodic job on a NAS must declare it ``kind="cron"``.

Refusal, not failure
--------------------
On such a host the verbs must REFUSE with a named reason and a DISTINCT
exit code (:data:`EXIT_UNSUPPORTED_HOST`), so a caller can tell "impossible
here" from "tried and broke". A raw ``systemctl: command not found`` reads
as a transient error and invites a retry loop that can never succeed.

launchd is a fourth case, not a gap
-----------------------------------
mba is macOS. There is NO launchd backend today and this module does not
pretend otherwise: it reports ``mechanism="launchd"`` with
``available=False`` so the refusal names launchd by name rather than
claiming the host is broken. Adding the backend later means adding one
branch to :func:`probe_supervision` and one installer — the mechanism is
already a first-class value here rather than a boolean, precisely so that
addition is not a restructuring.

Why the supervisor scan is mechanism-BLIND
------------------------------------------
Measured on the head node, concurrently, for the same process::

    */2 * * * * ~/.scitex/agent-container/bin/sac-listen-watch.sh …  # sac-listen-supervisor
    sac-listen.service   loaded active running

A crontab watchdog AND a systemd unit, supervising one daemon. A check
that only looked for a conflicting *unit* would have seen nothing wrong
and installed a THIRD supervisor. :func:`find_supervisors` therefore scans
unit files, the crontab, AND the respawn pidfile, and matches the crontab
by a normalised slug (``sac.listen`` -> ``sac-listen``) because the real
line names the script, not the JobSpec.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import click

#: Exit code for "this host cannot run this kind of job at all".
#: Distinct from 1 (generic failure) and 2 (usage / unconfirmed write) so a
#: caller can branch on impossibility without parsing prose.
EXIT_UNSUPPORTED_HOST = 3

#: Exit code for "something already supervises this job".
EXIT_CONFLICTING_SUPERVISOR = 4

#: Marker written into every unit this package generates
#: (``_systemd._DOC_URL``). Its presence is how we tell OUR unit from a
#: hand-written one we must not clobber.
_OUR_UNIT_MARKER = "https://github.com/scitex-ai/scitex-dev"

_CRON_ONLY_REMEDY = (
    "kind='cron' is the only mechanism available on every fleet host; "
    "declare the job as kind='cron', or supervise it with "
    "`scitex-dev service ensure <name> --respawn` (a keep-alive loop "
    "under ~/.scitex/<pkg>/runtime/ that needs no init system)."
)


@dataclass(frozen=True)
class Supervision:
    """What supervises user daemons on THIS host, and whether we can use it.

    ``mechanism`` is a NAME, never a boolean, so a future launchd backend
    slots in as a new value instead of a second flag.
    """

    available: bool
    mechanism: str  # "systemd-user" | "launchd" | "none"
    reason: str
    remedy: str


def unit_dir(home: Path | None = None) -> Path:
    """Resolve ``~/.config/systemd/user`` honouring ``$HOME`` (test seam)."""
    base = home if home is not None else Path.home()
    return base / ".config" / "systemd" / "user"


def probe_supervision(
    *,
    platform: str | None = None,
    which=shutil.which,
    run_fn=None,
) -> Supervision:
    """Report whether this host can supervise ``service``/``timer`` jobs.

    ``platform`` / ``which`` / ``run_fn`` are injection seams; the defaults
    probe the real host. Tests prefer setting a real empty ``PATH`` over
    passing ``which``, so the probe under test is the production one.
    """
    plat = platform if platform is not None else sys.platform

    if plat == "darwin":
        return Supervision(
            available=False,
            mechanism="launchd",
            reason=(
                "this host is macOS, which supervises user daemons with "
                "launchd, not `systemd --user`. scitex-dev ships no launchd "
                "backend, so kind='service'/'timer' cannot be installed here"
            ),
            remedy=_CRON_ONLY_REMEDY,
        )

    if which("systemctl") is None:
        return Supervision(
            available=False,
            mechanism="none",
            reason=(
                "no `systemctl` on PATH — this host has no systemd at all "
                "(measured on scitex-nas-01/-02, which are Synology/QNAP "
                "appliances). kind='service'/'timer' cannot be installed here"
            ),
            remedy=_CRON_ONLY_REMEDY,
        )

    from ....jobs._ensure import systemd_user_available

    if not systemd_user_available(run_fn=run_fn):
        return Supervision(
            available=False,
            mechanism="none",
            reason=(
                "`systemctl` exists but the `--user` manager did not answer "
                "— there is no user session bus for this uid (a headless "
                "login with no lingering session is the usual cause)"
            ),
            remedy=(
                "enable a persistent user session with `loginctl "
                "enable-linger $USER` and re-run, or " + _CRON_ONLY_REMEDY
            ),
        )

    return Supervision(
        available=True,
        mechanism="systemd-user",
        reason="systemd --user manager is reachable",
        remedy="",
    )


def require_supervision(kind: str, verb: str, sup: Supervision) -> None:
    """Abort with a NAMED refusal when ``sup`` reports the host cannot help.

    Writes to stderr and exits :data:`EXIT_UNSUPPORTED_HOST`. Never raises
    ``ClickException`` — that would exit 1 and be indistinguishable from a
    job that genuinely failed.
    """
    if sup.available:
        return
    click.echo(
        f"refusing: `{kind} {verb}` is not supported on this host "
        f"(mechanism={sup.mechanism}).",
        err=True,
    )
    click.echo(f"  reason: {sup.reason}.", err=True)
    click.echo(f"  remedy: {sup.remedy}", err=True)
    raise SystemExit(EXIT_UNSUPPORTED_HOST)


@dataclass(frozen=True)
class Supervisor:
    """One thing currently supervising a job, whatever the mechanism."""

    mechanism: str  # "systemd-unit" | "crontab" | "respawn"
    locus: str  # unit path, crontab line, or pidfile path
    ours: bool  # did scitex-dev write it?

    def describe(self) -> str:
        owner = "scitex-dev-managed" if self.ours else "FOREIGN"
        return f"{self.mechanism} [{owner}] {self.locus}"


def _slug(name: str) -> str:
    """Normalise a JobSpec name for crontab matching.

    ``sac.listen`` -> ``sac-listen``. The live conflicting cron line names
    the script (``sac-listen-watch.sh``), not the JobSpec, so an exact-name
    search finds nothing while the daemon has two supervisors.
    """
    return name.replace(".", "-").replace("_", "-").lower()


def find_supervisors(
    job,
    *,
    home: Path | None = None,
    crontab_text: str | None = None,
) -> list[Supervisor]:
    """Return every supervisor of ``job`` found on this host, any mechanism.

    ``crontab_text`` is an injection seam; when ``None`` the real crontab is
    read through ``_cli.cron._crontab.read_crontab_state`` (which reports
    "could not look" rather than inventing an empty crontab).
    """
    found: list[Supervisor] = []
    found.extend(_unit_supervisors(job, home=home))
    found.extend(_cron_supervisors(job, crontab_text=crontab_text))
    found.extend(_respawn_supervisors(job, home=home))
    return found


def _unit_supervisors(job, *, home: Path | None) -> list[Supervisor]:
    out: list[Supervisor] = []
    base = unit_dir(home)
    for suffix in (".service", ".timer"):
        path = base / f"{job.name}{suffix}"
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        out.append(
            Supervisor(
                mechanism="systemd-unit",
                locus=str(path),
                ours=_OUR_UNIT_MARKER in text,
            )
        )
    return out


def _cron_supervisors(job, *, crontab_text: str | None) -> list[Supervisor]:
    """Any crontab line that plausibly supervises ``job``.

    Deliberately BROAD: a hand-rolled watchdog names its own script, so an
    exact JobSpec-name search is the check that missed the live double
    supervision on the head node.
    """
    if crontab_text is None:
        from ...cron._crontab import read_crontab_state

        state = read_crontab_state()
        if not state.readable:
            return []
        crontab_text = state.text

    from ....jobs._cron_block import LINE_MARKER_PREFIX

    needle = _slug(job.name)
    ours_marker = f"{LINE_MARKER_PREFIX}{job.name}"
    out: list[Supervisor] = []
    for raw in crontab_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if needle not in _slug(line):
            continue
        out.append(
            Supervisor(
                mechanism="crontab",
                locus=line,
                ours=ours_marker in raw,
            )
        )
    return out


def _respawn_supervisors(job, *, home: Path | None) -> list[Supervisor]:
    from ....jobs import _respawn
    from ....jobs._ensure import _pidfile_alive

    pidf = _respawn.pidfile_path(job, home=home)
    if not _pidfile_alive(pidf):
        return []
    return [Supervisor(mechanism="respawn", locus=str(pidf), ours=True)]


def guard_existing_supervisors(
    job,
    *,
    adopt: bool,
    force: bool,
    home: Path | None = None,
    crontab_text: str | None = None,
) -> bool:
    """Decide whether ``install`` may write for ``job``. Returns ``proceed``.

    Three outcomes, and the DEFAULT is the safe one:

    * nothing supervises the job          -> ``True`` (write)
    * something does, and ``--adopt``     -> ``False`` (leave it; report)
    * something does, and ``--force``     -> ``True`` (write, report loudly)
    * something does, neither flag        -> abort
      :data:`EXIT_CONFLICTING_SUPERVISOR`

    A rename/reinstall that silently overwrote would produce two supervisors
    fighting over one process. For ``sac.accounts-refresh`` — the fleet's
    SOLE OAuth refresher, whose refresh token is SINGLE-USE — two racing
    refreshers revoke each other and expire every account within hours. So
    the default REFUSES and names what it found.
    """
    existing = find_supervisors(job, home=home, crontab_text=crontab_text)
    if not existing:
        return True

    lines = [f"  {s.describe()}" for s in existing]

    if adopt:
        click.echo(
            f"adopt: {job.name} is already supervised; writing nothing.",
            err=True,
        )
        for line in lines:
            click.echo(line, err=True)
        return False

    if force:
        click.echo(
            f"force: {job.name} is already supervised — overwriting anyway. "
            f"Verify EXACTLY ONE supervisor survives before you walk away.",
            err=True,
        )
        for line in lines:
            click.echo(line, err=True)
        return True

    click.echo(
        f"refusing: {job.name} is already supervised by "
        f"{len(existing)} mechanism(s). Installing now would add a "
        f"COMPETING supervisor.",
        err=True,
    )
    for line in lines:
        click.echo(line, err=True)
    click.echo(
        "  Use --adopt to keep the existing supervisor (writes nothing), "
        "or --force to overwrite. A rename/reinstall must be "
        "stop-old -> remove-old -> install-new -> verify-exactly-one.",
        err=True,
    )
    raise SystemExit(EXIT_CONFLICTING_SUPERVISOR)


__all__ = [
    "EXIT_CONFLICTING_SUPERVISOR",
    "EXIT_UNSUPPORTED_HOST",
    "Supervision",
    "Supervisor",
    "find_supervisors",
    "guard_existing_supervisors",
    "probe_supervision",
    "require_supervision",
    "unit_dir",
]


# EOF
