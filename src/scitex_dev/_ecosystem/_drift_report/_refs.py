#!/usr/bin/env python3
"""Read a version from the REF ITS LABEL NAMES, not from local HEAD.

Two columns of this report named a remote authority and computed a local
artifact, and both were wrong in the same direction on 2026-08-16:

    label                                  value it actually produced
    "SSoT = pyproject.toml @ local develop"  the WORKING TREE, any branch,
                                             uncommitted edits included
    "GitHub: latest release tag (what       `git describe --abbrev=0` — the
     `main` shipped)"                        newest tag reachable from HEAD

Measured on ywata-note-win, which produced that night's fleet baseline:
15 of 84 checkouts were off their default branch and 24 were dirty, so the
reference column was mislabelled for a fifth of the fleet. scitex-cards read
0.38.0 where `origin/main` was 0.41.0 — not staleness (the clone was fetched
that day and held 143 tags) but REACHABILITY: v0.40.0 and v0.41.0 were cut on
main and never merged back, so `describe` walked past them.

The generalisation, from scitex-agent-container, who found a third instance
in their own card store: *a remote authority named in the label, a local
artifact in the value.* Their detector is the cheap one — for any such field,
ask what the value would be if the code ran on a different machine or a
different branch. If the answer changes, the label is lying.

So every reader here takes an explicit ref and REFUSES rather than falling
back to something closer to hand. A refusal shows up as ``NOT JUDGEABLE``,
which this report already renders honestly; a silent substitution shows up as
a verdict, which is what cost the fleet a wrong baseline.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Why a reading is missing. Never collapse these into ``None`` alone: "no
#: git repo" and "ref does not exist" call for different fixes, and the
#: report says so rather than rendering both as absence.
PROV_REF = "ref"
PROV_NO_REPO = "no-repo"
PROV_NO_REF = "no-ref"
PROV_NO_FILE = "no-file"
PROV_ERROR = "error"

#: The SSoT ref -- "what SHOULD the version be". Local ``develop`` first,
#: because a develop checkout legitimately runs ahead of its remote and that
#: is the state the fleet is converging TO.
DEVELOP_REFS: tuple[str, ...] = ("develop", "origin/develop")

#: The released ref -- "what did main ship". ``origin/main`` first, because
#: the question is about what is PUBLISHED, and a local ``main`` can trail
#: the remote without anyone noticing.
MAIN_REFS: tuple[str, ...] = ("origin/main", "main")

_TIMEOUT = 20


@dataclass(frozen=True)
class RefReading:
    """A value together with WHERE it came from, or why it is absent."""

    value: str | None
    provenance: str
    ref: str
    note: str = ""

    @property
    def known(self) -> bool:
        return self.value is not None


def _git(repo: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return 1, str(exc)
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _is_repo(repo: Path | None) -> bool:
    return bool(repo) and (Path(repo) / ".git").exists()


def resolve_ref(repo: Path, candidates: tuple[str, ...]) -> str | None:
    """First ref in ``candidates`` that EXISTS, else None.

    Ordered preference is not a fallback to a different KIND of thing --
    every candidate here names the same concept (``develop``,
    ``origin/develop``). Falling back from a ref to the working tree is the
    defect this module exists for; falling back between two spellings of the
    same ref is not.
    """
    for ref in candidates:
        rc, _ = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if rc == 0:
            return ref
    return None


def version_at_ref(
    repo: Path | None, candidates: tuple[str, ...]
) -> RefReading:
    """``pyproject.toml`` version as committed on the named ref."""
    label = "/".join(candidates)
    if not _is_repo(repo):
        return RefReading(None, PROV_NO_REPO, label, "not a git checkout")
    repo = Path(repo)

    ref = resolve_ref(repo, candidates)
    if ref is None:
        return RefReading(None, PROV_NO_REF, label, f"no ref among {label}")

    rc, out = _git(repo, "show", f"{ref}:pyproject.toml")
    if rc != 0:
        return RefReading(None, PROV_NO_FILE, ref, "no pyproject.toml on ref")

    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("version") and "=" in stripped:
            value = stripped.split("=", 1)[1].strip().strip("\"'")
            if value:
                return RefReading(value, PROV_REF, ref)
    return RefReading(None, PROV_NO_FILE, ref, "no version key on ref")


def latest_tag_at_ref(
    repo: Path | None, candidates: tuple[str, ...], *, match: str = "v*"
) -> RefReading:
    """Newest version tag REACHABLE FROM the named ref.

    Reachability is the whole point. ``git describe`` walks backwards from a
    commit, so a tag cut on a branch that was never merged back is invisible
    to it -- which is exactly how a release-bearing tag went unseen while
    sitting in the same clone.
    """
    label = "/".join(candidates)
    if not _is_repo(repo):
        return RefReading(None, PROV_NO_REPO, label, "not a git checkout")
    repo = Path(repo)

    ref = resolve_ref(repo, candidates)
    if ref is None:
        return RefReading(None, PROV_NO_REF, label, f"no ref among {label}")

    rc, out = _git(repo, "describe", "--tags", "--abbrev=0", "--match", match, ref)
    if rc != 0 or not out:
        return RefReading(None, PROV_NO_REF, ref, "no version tag reachable")
    return RefReading(out, PROV_REF, ref)


def newest_tag_in_clone(repo: Path | None, *, match: str = "v*") -> str | None:
    """Newest version tag ANYWHERE in the clone, ignoring reachability."""
    if not _is_repo(repo):
        return None
    rc, out = _git(Path(repo), "tag", "-l", match, "--sort=-v:refname")
    if rc != 0 or not out:
        return None
    return out.splitlines()[0].strip()


def unreachable_tag_note(reading: RefReading, newest: str | None) -> str:
    """Say so when a NEWER tag exists that the named ref cannot see.

    This is a fact about the repo's branch topology (main and develop have
    diverged on releases), and it is the difference between "nothing newer
    was released" and "something newer was released somewhere this ref
    cannot reach". Rendering both as the same number is what made the
    defect invisible.
    """
    if newest is None or not reading.known or newest == reading.value:
        return ""
    return f"tag {newest} exists but is not reachable from {reading.ref}"
