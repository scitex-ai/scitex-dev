#!/usr/bin/env python3
# Timestamp: 2026-07-23
# File: scitex_dev/_ecosystem/_enumerate.py

"""Distribution-identity enumeration for the SciTeX ecosystem.

``ECOSYSTEM`` (see ``_registry``) answers *"which local directories has
somebody written down"*. Every brand-wide operation, though, asks a
different question: *"which DISTRIBUTIONS exist"*. The two answers differ
in three measured ways, and this module exists to close each one:

(a) OMISSION — a repo in the GitHub org with no registry entry simply
    vanished from every sweep. :func:`enumerate_distributions` accepts an
    ``org_repos`` listing and reports the delta as ``checked_out=False``
    distributions instead of dropping them.

(b) DOUBLE-COUNTING — two directories can be two checkouts of ONE repo
    (``~/proj/scitex-io`` and ``~/proj/scitex-io-dotscitex`` both have
    origin ``scitex-ai/scitex-io``), and a linked git worktree is a third
    way to spell the same distribution. Identity here is the **origin
    remote**, never the directory name; extra paths are reported as
    ALIASES on the canonical distribution rather than counted again — and
    never silently dropped.

(c) STALENESS — figures collected from a local checkout describe whatever
    commit that tree sits on, which may be behind ``origin``. The result
    carries an explicit :attr:`Enumeration.measured_tree` label so a
    caller can tell what was measured WITHOUT reading this source.

Nothing here degrades silently: a path whose git metadata cannot be read
is recorded in :attr:`Enumeration.errors` AND surfaced as an
``unresolved`` entry, so the list can never quietly get shorter.

Canonical-checkout rule (deterministic, documented, tested)
-----------------------------------------------------------
Among the checkouts sharing one origin remote:

1. linked git worktrees are never canonical (they are always aliases);
2. otherwise prefer the path whose directory basename equals the repo
   name (``~/proj/scitex-io`` beats ``~/proj/scitex-io-dotscitex``);
3. otherwise the first path in sorted absolute-path order.

Ties cannot occur: rule 3 is a total order over distinct paths.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

__all__ = [
    "Alias",
    "Distribution",
    "Enumeration",
    "MEASURED_LOCAL_CHECKOUT",
    "enumerate_distributions",
    "fetch_org_repos",
    "normalize_remote",
    "read_origin",
    "registry_checkout_paths",
    "scan_checkout_root",
]


# Label used when figures describe local working trees at whatever commit
# they happen to sit on (as opposed to ``origin/<default-branch>``).
MEASURED_LOCAL_CHECKOUT = (
    "local-checkouts (each at its own current commit; may lag origin)"
)

_GIT_URL_RE = re.compile(
    r"""^
    (?:
        (?:git\+)?(?:https?|ssh|git)://(?:[^@/]+@)?[^/]+/   # scheme://host/
      | (?:[^@/\s]+@)?[^:/\s]+:                            # scp-like host:
      | file://
    )?
    (?P<path>[^\s]+?)
    (?:\.git)?
    /?$
    """,
    re.VERBOSE,
)


def normalize_remote(url: str) -> Optional[str]:
    """Return a canonical ``owner/name`` identity for a git remote URL.

    All spellings of one repo collapse to one string::

        git@github.com:scitex-ai/scitex-io.git  -> scitex-ai/scitex-io
        https://github.com/scitex-ai/scitex-io  -> scitex-ai/scitex-io
        ssh://git@github.com/scitex-ai/scitex-io.git -> scitex-ai/scitex-io

    A local-path remote (no host) keeps its resolved absolute path as the
    identity, so two clones of one on-disk repo still collapse. Returns
    ``None`` for an empty/unparseable URL — the caller records that as an
    error rather than guessing.
    """
    if not url or not url.strip():
        return None
    url = url.strip()
    match = _GIT_URL_RE.match(url)
    if match is None:
        return None
    path = match.group("path").strip("/")
    if not path:
        return None
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and not url.startswith(("/", ".", "file://")):
        return "/".join(parts[-2:]).lower()
    # Bare local path remote — identity is the resolved location.
    try:
        return str(Path(url).expanduser().resolve())
    except OSError:  # pragma: no cover - resolve() on a broken mount
        return url


def _run_git(path: Path, args: Sequence[str], timeout: float = 20.0):
    """Run ``git -C <path> <args>``; return the CompletedProcess."""
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def read_origin(path: Path) -> tuple[Optional[str], Optional[str]]:
    """Return ``(normalized_repo, error)`` for the ``origin`` remote of ``path``.

    Exactly one of the two is non-``None``. The error string is kept so
    the caller can SAY that a path failed instead of shortening its list.
    """
    path = Path(path)
    if not path.is_dir():
        return None, f"not a directory: {path}"
    try:
        proc = _run_git(path, ["remote", "get-url", "origin"])
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git failed for {path}: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return None, f"no origin remote for {path}: {detail[0] if detail else '?'}"
    repo = normalize_remote(proc.stdout)
    if repo is None:
        return None, f"unparseable origin URL for {path}: {proc.stdout.strip()!r}"
    return repo, None


def _is_linked_worktree(path: Path) -> bool:
    """True iff ``path`` is a LINKED git worktree (not the main checkout).

    A linked worktree stores a ``.git`` FILE containing a ``gitdir:``
    pointer into ``<main>/.git/worktrees/<name>``; the main checkout has a
    ``.git`` DIRECTORY. Read structurally — no git invocation, so this
    still classifies correctly when git itself is unavailable.
    """
    dot_git = Path(path) / ".git"
    if not dot_git.is_file():
        return False
    try:
        text = dot_git.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "/worktrees/" in text or "\\worktrees\\" in text


@dataclass
class Alias:
    """A non-canonical path that resolves to an already-counted distribution."""

    path: str
    reason: str  # "duplicate-checkout" | "worktree"

    def to_dict(self) -> dict:
        return {"path": self.path, "reason": self.reason}


@dataclass
class Distribution:
    """One distribution — identified by its origin remote, not its directory."""

    repo: str
    registry_name: Optional[str] = None
    canonical_path: Optional[str] = None
    aliases: List[Alias] = field(default_factory=list)
    checked_out: bool = True
    in_registry: bool = False
    in_org: bool = False

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "registry_name": self.registry_name,
            "canonical_path": self.canonical_path,
            "aliases": [a.to_dict() for a in self.aliases],
            "alias_count": len(self.aliases),
            "checked_out": self.checked_out,
            "in_registry": self.in_registry,
            "in_org": self.in_org,
        }


@dataclass
class Enumeration:
    """A LABELLED enumeration result — says what it is, not just a list.

    ``counts`` distinguishes directories scanned from distributions found,
    so a caller can tell a complete enumeration from a filtered one
    without reading this source.
    """

    distributions: List[Distribution]
    directories_scanned: int
    aliases_collapsed: int
    measured_tree: str
    org: Optional[str] = None
    org_listing_available: bool = False
    errors: List[str] = field(default_factory=list)
    unresolved_paths: List[str] = field(default_factory=list)

    @property
    def distribution_count(self) -> int:
        return len(self.distributions)

    @property
    def not_checked_out(self) -> List[Distribution]:
        return [d for d in self.distributions if not d.checked_out]

    def to_dict(self) -> dict:
        return {
            "kind": "distributions",
            "measured_tree": self.measured_tree,
            "org": self.org,
            "org_listing_available": self.org_listing_available,
            "counts": {
                "directories_scanned": self.directories_scanned,
                "distributions": self.distribution_count,
                "aliases_collapsed": self.aliases_collapsed,
                "not_checked_out": len(self.not_checked_out),
                "errors": len(self.errors),
            },
            "distributions": [d.to_dict() for d in self.distributions],
            "errors": list(self.errors),
            "unresolved_paths": list(self.unresolved_paths),
        }

    def summary_line(self) -> str:
        """One self-describing line — the label a caller reads first."""
        return (
            f"{self.distribution_count} distribution(s) from "
            f"{self.directories_scanned} director(ies): "
            f"{self.aliases_collapsed} alias(es) collapsed, "
            f"{len(self.not_checked_out)} org repo(s) with no local checkout, "
            f"{len(self.errors)} unreadable path(s). "
            f"Measured tree: {self.measured_tree}."
        )


def registry_checkout_paths() -> Dict[str, str]:
    """Return ``{registry_name: expanded_local_path}`` for every registry entry.

    Registry entries are the *declared* checkouts. Identity resolution
    still happens by origin remote — a registry name is metadata attached
    to a distribution, never the distribution's identity.
    """
    from ._registry import ECOSYSTEM

    out: Dict[str, str] = {}
    for name, info in ECOSYSTEM.items():
        local = info.get("local_path")
        if not local:
            continue
        out[name] = str(Path(local).expanduser())
    return out


def scan_checkout_root(root: str) -> List[str]:
    """Return every immediate child of ``root`` that is a git checkout.

    This is the DIRECTORY-shaped input that brand-wide sweeps actually
    use, and the input where double-counting bites: a scan of
    ``~/proj`` sees ``scitex-io`` and ``scitex-io-dotscitex`` as two
    things. Feed the result to :func:`enumerate_distributions` to get
    distributions back out. Sorted for determinism.
    """
    base = Path(root).expanduser()
    if not base.is_dir():
        return []
    out: List[str] = []
    for child in sorted(base.iterdir()):
        try:
            if child.is_dir() and (child / ".git").exists():
                out.append(str(child))
        except OSError:  # pragma: no cover - unreadable mount entry
            continue
    return out


def fetch_org_repos(org: str, timeout: float = 60.0) -> tuple[List[str], Optional[str]]:
    """Return ``(repos, error)`` — ``owner/name`` for every repo in ``org``.

    Uses ``gh repo list``. On failure the repo list is EMPTY and the error
    is non-``None``; callers must surface it rather than treat an empty
    listing as "the org has no extra repos".
    """
    try:
        proc = subprocess.run(
            ["gh", "repo", "list", org, "--limit", "1000", "--json", "nameWithOwner"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"gh repo list {org} failed: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return [], f"gh repo list {org} exited {proc.returncode}: " + (
            detail[0] if detail else "?"
        )
    import json as _json

    try:
        rows = _json.loads(proc.stdout or "[]")
    except ValueError as exc:
        return [], f"gh repo list {org} returned unparseable JSON: {exc}"
    return [str(r["nameWithOwner"]).lower() for r in rows if r.get("nameWithOwner")], None


def _pick_canonical(candidates: List[tuple[str, bool]], repo: str) -> str:
    """Apply the documented canonical-checkout rule; return the winning path.

    ``candidates`` is ``[(path, is_worktree), ...]``. See the module
    docstring for the rule this implements.
    """
    non_worktrees = [p for p, wt in candidates if not wt]
    pool = non_worktrees or [p for p, _ in candidates]
    repo_name = repo.rsplit("/", 1)[-1]
    by_name = sorted(p for p in pool if Path(p).name == repo_name)
    if by_name:
        return by_name[0]
    return sorted(pool)[0]


def enumerate_distributions(
    paths: Optional[Iterable[str]] = None,
    org_repos: Optional[Iterable[str]] = None,
    org: Optional[str] = None,
    org_error: Optional[str] = None,
    measured_tree: str = MEASURED_LOCAL_CHECKOUT,
) -> Enumeration:
    """Resolve checkout ``paths`` into DISTRIBUTIONS keyed by origin remote.

    Parameters
    ----------
    paths
        Checkout directories to resolve. Defaults to every registry
        ``local_path``.
    org_repos
        ``owner/name`` listing for the org, used to surface repos with no
        local checkout. ``None`` means "no listing supplied" — the result
        then reports ``org_listing_available=False`` so a caller cannot
        mistake an unqueried org for an empty delta.
    org, org_error
        Recorded on the result for labelling / error surfacing.
    measured_tree
        Human-readable statement of WHICH tree the figures describe.

    Two paths whose ``origin`` resolves to the same repo are ONE
    distribution; the non-canonical ones appear as ``aliases``. Two
    genuinely distinct repos stay TWO distributions.
    """
    registry = registry_checkout_paths()
    path_to_registry = {v: k for k, v in registry.items()}
    if paths is None:
        path_list = sorted(registry.values())
    else:
        path_list = sorted({str(Path(p).expanduser()) for p in paths})

    errors: List[str] = []
    unresolved: List[str] = []
    grouped: Dict[str, List[tuple[str, bool]]] = {}

    for path in path_list:
        repo, error = read_origin(Path(path))
        if repo is None:
            if _is_linked_worktree(Path(path)):
                # An orphaned linked worktree: its .git file still points at a
                # main checkout that has moved or gone. Say WHICH failure this
                # is — a caller must not read it as a distinct distribution.
                error = f"orphaned-worktree (unresolvable gitdir): {error}"
            errors.append(error or f"unresolved: {path}")
            unresolved.append(path)
            continue
        grouped.setdefault(repo, []).append((path, _is_linked_worktree(Path(path))))

    org_list = [r.lower() for r in org_repos] if org_repos is not None else None

    distributions: List[Distribution] = []
    aliases_collapsed = 0
    for repo in sorted(grouped):
        candidates = grouped[repo]
        canonical = _pick_canonical(candidates, repo)
        aliases = [
            Alias(path=p, reason="worktree" if wt else "duplicate-checkout")
            for p, wt in sorted(candidates)
            if p != canonical
        ]
        aliases_collapsed += len(aliases)
        registry_name = path_to_registry.get(canonical)
        if registry_name is None:
            for p, _ in sorted(candidates):
                if p in path_to_registry:
                    registry_name = path_to_registry[p]
                    break
        distributions.append(
            Distribution(
                repo=repo,
                registry_name=registry_name,
                canonical_path=canonical,
                aliases=aliases,
                checked_out=True,
                in_registry=registry_name is not None,
                in_org=org_list is not None and repo in org_list,
            )
        )

    if org_list is not None:
        seen = set(grouped)
        for repo in sorted(set(org_list) - seen):
            distributions.append(
                Distribution(
                    repo=repo,
                    registry_name=None,
                    canonical_path=None,
                    aliases=[],
                    checked_out=False,
                    in_registry=False,
                    in_org=True,
                )
            )

    if org_error:
        errors.append(org_error)

    return Enumeration(
        distributions=distributions,
        directories_scanned=len(path_list),
        aliases_collapsed=aliases_collapsed,
        measured_tree=measured_tree,
        org=org,
        org_listing_available=org_list is not None,
        errors=errors,
        unresolved_paths=unresolved,
    )


# EOF
