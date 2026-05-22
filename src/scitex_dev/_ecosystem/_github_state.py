#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ecosystem GitHub-state audits (live `gh api` checks).

Unlike the per-file ``audit-project`` rules (which read the repo working
tree), these rules inspect *GitHub state* that has no local file
counterpart — currently the repository's default branch.

PS-172 — default-branch convention
-----------------------------------
Every SciTeX repository's GitHub default branch must be ``main``.

Convention (operator decision, msg 3893): ``main`` is the public
default a visitor sees on GitHub; ``develop`` is the integration branch
where active work lands and tag pushes fast-forward ``main``. A repo
left defaulting to ``develop`` exposes integration WIP as the public
face and breaks the "main = latest release" expectation downstream
consumers rely on.

Design: the checker takes a ``fetch_default_branch`` callable so it can
be unit-tested against a real recorded API shape (a dict) with **no
mocks**. The production default shells out to ``gh api``.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable

# The convention the ecosystem enforces.
CONVENTION_DEFAULT_BRANCH = "main"

# Sentinel returned by the fetcher when the repo cannot be queried
# (404, network error, auth). Distinguished from a real branch so the
# audit reports "unknown" rather than a false "deviates".
UNKNOWN = "<unknown>"


@dataclass(frozen=True)
class DefaultBranchFinding:
    """One repo's default-branch audit result."""

    package: str
    repo: str  # owner/name
    default_branch: str  # actual GitHub default, or UNKNOWN
    expected: str  # the convention (CONVENTION_DEFAULT_BRANCH)

    @property
    def ok(self) -> bool:
        return self.default_branch == self.expected

    @property
    def unknown(self) -> bool:
        return self.default_branch == UNKNOWN

    @property
    def deviates(self) -> bool:
        """True only for a *known* default branch that is not the convention."""
        return not self.unknown and not self.ok


def gh_default_branch(repo: str) -> str:
    """Production fetcher: query GitHub for ``repo``'s default branch.

    ``repo`` is ``owner/name``. Returns the branch name on success, or
    :data:`UNKNOWN` on any failure (404, missing ``gh``, timeout, auth).
    Honours ``GH_TOKEN`` from the environment if set (caller's job).
    """
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{repo}", "--jq", ".default_branch"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return UNKNOWN
    if proc.returncode != 0:
        return UNKNOWN
    branch = (proc.stdout or "").strip()
    return branch or UNKNOWN


def audit_default_branches(
    repos: Iterable[tuple[str, str]],
    *,
    fetch_default_branch: Callable[[str], str] = gh_default_branch,
    expected: str = CONVENTION_DEFAULT_BRANCH,
) -> list[DefaultBranchFinding]:
    """Audit each ``(package, repo)`` pair's GitHub default branch.

    ``repos`` is an iterable of ``(package_name, owner/repo)`` tuples.
    ``fetch_default_branch`` is injected so tests pass a real
    dict-backed callable instead of touching the network. Returns one
    :class:`DefaultBranchFinding` per repo, order-preserving.
    """
    findings: list[DefaultBranchFinding] = []
    for package, repo in repos:
        branch = fetch_default_branch(repo)
        findings.append(
            DefaultBranchFinding(
                package=package,
                repo=repo,
                default_branch=branch,
                expected=expected,
            )
        )
    return findings
