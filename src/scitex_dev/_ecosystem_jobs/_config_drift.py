#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does the file an agent ACTUALLY READS equal what the ref says?

THE MEASURED SUBJECT IS THE DEPLOYED PATH, NOT THE REPOSITORY. That is the
whole point of this job, and the first tool written for it got it wrong.

Governance reaches an agent through THREE hops, and it can stop silently at
any of them::

    merged    the ref has it
    pulled    this host's clone has it          (merged is not pulled)
    deployed  the path the agent opens has it   (pulled is not deployed)

All three were hit by the SAME FIVE LINES of constitution text on 2026-08-20:
first an unpushed live edit on one host; then four hosts five commits behind;
then — after they pulled — three hosts whose agents still read the old rule,
because ``~/.claude/commands`` there is a real directory holding a MATERIALISED
COPY that only a separate deploy refreshes. The fourth host had that path
SYMLINKED into the clone, so a pull landed instantly and it looked fine
throughout.

Why the third hop needs a machine and the first two do not
---------------------------------------------------------
* no actor — nobody edited anything;
* no event — nothing failed, the pull succeeded;
* no local symptom — the host reads the older rule and obeys it CORRECTLY;
* **and it passes a rigorous repository-side check.**

That last one is decisive. A ``sha256`` comparison of the clone's file returned
IN_SYNC on all four hosts while three were serving stale bytes to every agent
on them. The predicate was exact and needed no control; its SUBJECT was wrong.
Rigour does not rescue a wrong subject.

Corollary worth keeping in the output: two hosts at the SAME COMMIT served
different bytes. Identical HEAD does not mean identical content read. And the
symlinked host matches BY CONSTRUCTION — a host that cannot fail this check is
not a host that passes it, so the verdict says which layout it has.

Why bytes, and why there is no positive control
-----------------------------------------------
The first probe used ``grep`` for a line of the change. A proxy like that needs
a control, because it answers "absent" both when the text is absent AND when
the probe never ran — which it did twice in ten minutes (``rg`` missing on bare
hosts; a listing that hid a dotfile). ``sha256(live) == sha256(ref)`` needs no
control: there is no path by which a probe that did not run answers "same" — it
raises, and this job reports ``UNMEASURED``.

Prefer a predicate that cannot silently degrade over a proxy plus a guard
against its degrading.

The one way bytes can lie is the empty string: ``sha256`` of nothing is the
same on both sides, so two FAILED READS agree. Both sides are checked for it
explicitly (:data:`_EMPTY_SHA256`).

UNMEASURED IS NOT A PASS
------------------------
The failure this job exists to catch IS invisibility. Folding "could not
measure" into success would make the check commit the very error it detects, so
:class:`ConfigDriftRunResult.ok` is False whenever anything is unmeasured, and
the CLI exit code separates the two cases.

Credit: the three-layer split, the deployed-path subject and the
no-silent-degradation predicate are scitex-agent-container's, measured on the
hosts. This module is that work made periodic under the supervisor, per
scitex-dev ADR-0012 — there is no second place to put a periodic job.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from typing import TextIO

__all__ = [
    "ConfigDriftFinding",
    "ConfigDriftRunResult",
    "DEFAULT_PAIRS",
    "DEFAULT_HOSTS",
    "run_once",
]

#: sha256 of the empty string. Two failed reads both hash to this and would
#: otherwise compare EQUAL, reporting a clean match built from nothing.
_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

#: repo-relative path -> the path an agent actually opens. Both sides are
#: needed: the whole defect is that these can differ.
DEFAULT_PAIRS: tuple[tuple[str, str], ...] = (
    (
        "src/.claude/to_claude/commands/constitution.md",
        "$HOME/.claude/commands/constitution.md",
    ),
)

DEFAULT_HOSTS: tuple[str, ...] = (
    "scitex-compute-01",
    "scitex-compute-02",
    "scitex-compute-03",
    "scitex-compute-04",
)

DEFAULT_REPO_DIR = "$HOME/.dotfiles"
DEFAULT_REF = "origin/develop"

# Verdicts. Only IN_SYNC is a pass.
IN_SYNC = "IN_SYNC"
PULL_PENDING = "PULL_PENDING"
DEPLOY_PENDING = "DEPLOY_PENDING"
LIVE_AHEAD = "LIVE_AHEAD"
UNMEASURED = "UNMEASURED"
UNREACHABLE = "UNREACHABLE"


@dataclass(frozen=True)
class ConfigDriftFinding:
    """One (host, deployed path) verdict."""

    host: str
    deployed_path: str
    verdict: str
    detail: str = ""

    @property
    def is_pass(self) -> bool:
        return self.verdict == IN_SYNC

    @property
    def is_unmeasured(self) -> bool:
        """UNMEASURED and UNREACHABLE are both 'we do not know', never 'fine'."""
        return self.verdict in (UNMEASURED, UNREACHABLE)


@dataclass
class ConfigDriftRunResult:
    findings: list[ConfigDriftFinding] = field(default_factory=list)

    @property
    def drifted(self) -> list[ConfigDriftFinding]:
        return [f for f in self.findings if not f.is_pass and not f.is_unmeasured]

    @property
    def unmeasured(self) -> list[ConfigDriftFinding]:
        return [f for f in self.findings if f.is_unmeasured]

    @property
    def ok(self) -> bool:
        """True only when every host was MEASURED and every host is in sync.

        Deliberately False on unmeasured: see the module docstring. A check
        whose blind spot counts as success reproduces the defect it exists for.
        """
        return bool(self.findings) and not self.drifted and not self.unmeasured

    @property
    def exit_code(self) -> int:
        """0 = all serve the ref, 1 = drift, 2 = something unmeasured."""
        if self.unmeasured:
            return 2
        if self.drifted:
            return 1
        return 0 if self.findings else 2


# The remote body. Runs on each host; prints one `path|verdict|detail` line per
# pair. Kept as one script so a host is one round trip.
_REMOTE = r"""
set -uo pipefail
eval "d=$REPO_DIR"
[ -d "$d/.git" ] || { echo "-|UNMEASURED|no repo at $d"; exit 0; }

# Fetching is what makes "this host is behind" observable at all: without it
# the host compares against its own stale idea of the ref and reports in-sync.
git -C "$d" fetch -q --all 2>/dev/null || { echo "-|UNMEASURED|fetch failed"; exit 0; }
git -C "$d" rev-parse --verify -q "$REF" >/dev/null || { echo "-|UNMEASURED|no ref $REF"; exit 0; }

for pair in $PAIRS; do
  rel=${pair%%=*}
  eval "live=${pair#*=}"

  ref_sha=$(git -C "$d" show "$REF:$rel" 2>/dev/null | sha256sum | cut -d' ' -f1)
  if [ -z "$ref_sha" ] || [ "$ref_sha" = "$EMPTY_SHA" ]; then
    echo "$live|UNMEASURED|'$rel' empty or absent at $REF"; continue
  fi

  [ -f "$live" ] || { echo "$live|UNMEASURED|deployed path does not exist"; continue; }
  live_sha=$(sha256sum "$live" 2>/dev/null | cut -d' ' -f1)
  if [ -z "$live_sha" ] || [ "$live_sha" = "$EMPTY_SHA" ]; then
    echo "$live|UNMEASURED|deployed file empty or unreadable"; continue
  fi

  if [ "$live_sha" = "$ref_sha" ]; then
    # Name the layout: a symlinked host matches BY CONSTRUCTION and has no
    # deploy step to fail, which is not the same as a deploy that works.
    if [ -L "$(dirname "$live")" ] || [ -L "$live" ]; then layout=symlinked; else layout=copied; fi
    echo "$live|IN_SYNC|$(git -C "$d" rev-parse --short "$REF") ($layout)"
    continue
  fi

  # Diverged. Locate WHICH hop stopped, so the report names the fix.
  repo_sha=$(sha256sum "$d/$rel" 2>/dev/null | cut -d' ' -f1)
  if [ "$repo_sha" != "$ref_sha" ]; then
    if [ -n "$(git -C "$d" status --porcelain -- "$rel" 2>/dev/null)" ]; then
      echo "$live|LIVE_AHEAD|uncommitted edit in the clone - push it"
    else
      behind=$(git -C "$d" rev-list --count "HEAD..$REF" 2>/dev/null || echo '?')
      echo "$live|PULL_PENDING|clone is $behind commits behind $REF"
    fi
  else
    echo "$live|DEPLOY_PENDING|clone has it; deployed copy is stale - run the deploy"
  fi
done
"""


def _probe_host(
    host: str,
    *,
    repo_dir: str,
    ref: str,
    pairs: tuple[tuple[str, str], ...],
    timeout: int,
    runner=subprocess.run,
) -> list[ConfigDriftFinding]:
    """Measure one host. Never raises; an unusable host is UNMEASURED."""
    pairs_env = " ".join(f"{rel}={live}" for rel, live in pairs)
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={min(timeout, 30)}",
        host,
        f"REPO_DIR={shlex.quote(repo_dir)} REF={shlex.quote(ref)} "
        f"PAIRS={shlex.quote(pairs_env)} EMPTY_SHA={_EMPTY_SHA256} bash -s",
    ]
    try:
        proc = runner(
            argv,
            input=_REMOTE,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - a failed probe is a verdict, not a crash
        return [ConfigDriftFinding(host, "-", UNREACHABLE, f"{type(exc).__name__}: {exc}")]

    lines = [ln for ln in (proc.stdout or "").splitlines() if "|" in ln]
    if not lines:
        detail = (proc.stderr or "").strip().splitlines()
        return [
            ConfigDriftFinding(
                host, "-", UNREACHABLE, detail[-1] if detail else "ssh produced nothing"
            )
        ]

    findings: list[ConfigDriftFinding] = []
    for ln in lines:
        path, _, rest = ln.partition("|")
        verdict, _, detail_txt = rest.partition("|")
        findings.append(ConfigDriftFinding(host, path, verdict.strip(), detail_txt.strip()))
    return findings


def run_once(
    *,
    hosts: tuple[str, ...] = DEFAULT_HOSTS,
    repo_dir: str = DEFAULT_REPO_DIR,
    ref: str = DEFAULT_REF,
    pairs: tuple[tuple[str, str], ...] = DEFAULT_PAIRS,
    timeout: int = 60,
    out: TextIO | None = None,
    runner=subprocess.run,
) -> ConfigDriftRunResult:
    """Check every host, report per (host, path), and never call unknown 'fine'."""
    result = ConfigDriftRunResult()
    for host in hosts:
        result.findings.extend(
            _probe_host(
                host,
                repo_dir=repo_dir,
                ref=ref,
                pairs=pairs,
                timeout=timeout,
                runner=runner,
            )
        )

    if out is not None:
        for f in result.findings:
            out.write(f"{f.host:<20} {f.deployed_path:<44} {f.verdict:<15} {f.detail}\n")
        out.write("\n")
        if result.unmeasured:
            out.write(
                f"INCOMPLETE: {len(result.unmeasured)} host/path(s) could not be "
                "measured. This is NOT a pass.\n"
            )
        elif result.drifted:
            out.write(
                f"DRIFT: {len(result.drifted)} host/path(s) do not serve what {ref} says.\n"
            )
        else:
            out.write(f"OK: every host SERVES what {ref} says.\n")
    return result


# EOF
