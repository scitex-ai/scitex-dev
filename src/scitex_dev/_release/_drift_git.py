#!/usr/bin/env python3
"""Probe the checkout: is this editable install behind its upstream?

Split out of ``check_editable_drift`` so that module decides POLICY — how
loud to be, what to cache, when to stay quiet — and this one does the
MEASUREMENT. The fix for the cache key belongs here, beside the git calls
it is a key for.

Every name is re-exported from ``check_editable_drift``, so existing
importers (``versioning._editable``, ``_ecosystem._skills.skills``) are
unchanged.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

#: Resolved once. ``None`` means git is unavailable, which every probe
#: below treats as "cannot answer" rather than as "not behind".
_GIT = shutil.which("git")


def _editable_dir_from_meta(meta) -> Path | None:
    """Editable source dir from a Distribution's ``direct_url.json`` (PEP 610),
    or None. Shared with :mod:`scitex_dev.staleness` (path-aware callers pass
    their own resolved Distribution instead of a global name lookup)."""
    try:
        raw = meta.read_text("direct_url.json")
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not data.get("dir_info", {}).get("editable"):
        return None
    url = data.get("url", "")
    if url.startswith("file://"):
        return Path(url[len("file://") :])
    return None


def _editable_source_dir(distribution: str) -> Path | None:
    """Return the editable-install source directory, or None if not editable.

    Reads `<dist-info>/direct_url.json` per PEP 610.
    """
    try:
        from importlib.metadata import distribution as _dist
    except ImportError:
        return None
    try:
        meta = _dist(distribution)
    except Exception:
        return None
    return _editable_dir_from_meta(meta)


def _git_state_key(repo: Path) -> str | None:
    """The commits being compared, as the cache key. One `git rev-parse`.

    This replaces a composite-MTIME key, and the history is the argument
    for the change: an mtime is a PROXY for "did the state move", and the
    proxy has now been wrong twice, each time about a path nobody had
    enumerated.

      1. It keyed on `.git/HEAD` alone. `git fetch --tags` writes
         `.git/packed-refs` and never HEAD, so a tag fetch was invisible
         and the cache served a stale "ahead of v0.X". Fixed by adding
         packed-refs and refs/tags/ to the composite.
      2. It still omitted `.git/refs/heads/`. A FAST-FORWARD PULL advances
         `refs/heads/<branch>` while leaving `.git/HEAD` untouched, because
         HEAD is a symref whose CONTENT ("ref: refs/heads/develop") does
         not change when the branch moves.

    The second miss is the damaging one, and not because it is rarer: a
    fast-forward is the MODAL way a checkout becomes current. So the
    detector was blind exactly when it had good news and loud when nothing
    had happened — it kept naming a commit already an ancestor of HEAD, and
    its own prescribed remedy (`git pull --ff-only`) could not clear it.
    A warning whose fix cannot satisfy it is indistinguishable from one
    that is stuck on, and people stop reading it.

    So key on CONTENT. The HEAD sha and the upstream sha ARE the values
    `_compute_drift` compares, so a key built from them cannot be wrong
    about a case nobody thought of. Costs one subprocess (~5ms) against a
    ~1ms cache hit — the price of a key that does not need re-fixing every
    time git writes somewhere new.
    """
    if not (repo / ".git").exists():
        return None
    # One process, both shas. `@{u}` is the configured upstream.
    both = _run_git(repo, "rev-parse", "HEAD", "@{u}")
    if both:
        return ":".join(both.split())
    # No configured upstream (detached HEAD, or a branch tracking nothing).
    # HEAD alone still invalidates on every commit move, which is strictly
    # better than the mtime key this replaces.
    return _run_git(repo, "rev-parse", "HEAD") or None


# `_git_head_mtime` and `_git_state_mtime` are DELETED, not repointed. Both
# named a float mtime, and this function returns a sha pair — an alias would
# hand a caller the right value under a name that lies about its type, which
# is worse than the ImportError. Nothing in src/ or tests/ imports either
# (checked before removing); they were kept for an external caller that never
# materialised, which is the unused-menu-item the house rules warn about.


def _run_git(repo: Path, *args: str) -> str | None:
    if _GIT is None:
        return None
    try:
        result = subprocess.run(
            [_GIT, "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _is_completion_context() -> bool:
    """True when the current process is a Click shell-completion source eval.

    `.bashrc`/`.zshrc` typically embed
        eval "$(_SCITEX_DEV_COMPLETE=bash_source scitex-dev)"
    which runs scitex-dev on every shell startup. Emitting the drift line
    in that path produces an unwanted warning every time the user opens a
    new shell or types `bash`. The Click env var is a reliable signal.
    """
    # Match any `_<PROG>_COMPLETE=...` from `eval "$(_FOO_COMPLETE=bash_source foo)"`
    # — scitex-dev's drift checker is imported transitively whenever any
    # downstream tool (scitex-scholar, scitex-io, …) is invoked, including
    # during their own shell-completion sourcing. Without broad matching,
    # the drift line ends up in the completion candidate list and bash
    # treats it as one of the suggestions (symptom: "TAB needed twice").
    return any(k == "_CLICK_COMPLETE" or k.endswith("_COMPLETE") for k in os.environ)


def _upstream_ref(repo: Path) -> str | None:
    """Resolve the tracking upstream for HEAD (e.g. ``origin/develop``).

    Resolution order:
      1. The configured upstream via ``@{u}`` (``origin/<branch>``).
      2. ``origin/<current-branch>`` if such a remote-tracking ref exists.
      3. ``origin/HEAD``, then ``origin/develop`` / ``origin/main``.
    Returns None when nothing resolves (→ AXIS 1 stays silent, fail-safe).
    """
    ref = _run_git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if ref:
        return ref
    branch = _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    candidates: list[str] = []
    if branch and branch != "HEAD":
        candidates.append(f"origin/{branch}")
    head_ref = _run_git(repo, "rev-parse", "--abbrev-ref", "origin/HEAD")
    if head_ref:
        candidates.append(head_ref)
    candidates += ["origin/develop", "origin/main"]
    for cand in candidates:
        if _run_git(repo, "rev-parse", "--verify", "--quiet", cand) is not None:
            return cand
    return None


def _behind_upstream(repo: Path) -> int | None:
    """Commits the tracking upstream has that HEAD lacks (i.e. BEHIND count).

    Returns the behind count, 0 if level/ahead, or None when there is no
    resolvable upstream (→ stay silent, fail-safe). Uses only the LOCAL
    remote-tracking ref (as fresh as the last ``git fetch``) — no network.
    """
    upstream = _upstream_ref(repo)
    if not upstream:
        return None
    # `--left-right --count A...B` → "<left-only>\t<right-only>":
    # left = commits in upstream not in HEAD = BEHIND.
    counts = _run_git(
        repo, "rev-list", "--left-right", "--count", f"{upstream}...HEAD"
    )
    if not counts:
        return None
    parts = counts.split()
    if len(parts) != 2:
        return None
    return int(parts[0])


def _compute_drift(repo: Path, distribution: str = "scitex-dev") -> str | None:
    """Editable path — warn ONLY when the checkout is BEHIND its remote.

    "Stale" == a newer scitex-dev is available to pull, i.e. HEAD is behind
    ``origin/<branch>``. The remedy is CWD-independent + non-destructive:
    ``git -C <abs-repo-path> pull --ff-only`` — NEVER a bare ``git pull`` or
    ``--rebase`` (from another CWD those hit the wrong repo / rewrite work).

    Being AHEAD of the latest release tag (unreleased dev commits on
    ``develop``) is NORMAL and is NOT flagged — that was the reported false
    positive. Any git error / no upstream / not a repo → None (fail-safe).
    """
    try:
        behind = _behind_upstream(repo)
        if not behind:
            return None
        head = _run_git(repo, "rev-parse", "--short", "HEAD")
        if not head:
            return None
    except (ValueError, OSError):
        return None
    return (
        f"editable {distribution}: HEAD ({head}) is {behind} commit(s) behind "
        f"its remote — run: git -C {repo} pull --ff-only"
    )

