#!/usr/bin/env python3
# Timestamp: 2026-04-27
# File: scitex_dev/pypi.py

"""PyPI publishing for scitex ecosystem packages.

Two methods:
  - ``"tag-trigger-oidc"``: git-tag + push, fires the repo's
    ``.github/workflows/publish-pypi.yml`` (trusted publisher / OIDC).
    Preferred — no long-lived secrets.
  - ``"twine"``: local ``python -m build && twine upload`` using a PyPI
    API token. Fallback when OIDC isn't configured (e.g. when bootstrapping
    a new project before a trusted publisher can be attached, or when the
    PyPI pending-publisher form is bot-flagged).

Safety model: defaults to ``dry_run=True`` (preview only). Set ``confirm=True``
or ``dry_run=False`` to actually publish.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

PublishMethod = Literal["auto", "tag-trigger-oidc", "twine"]


@dataclass
class PublishResult:
    """Outcome of a single ``publish()`` call."""

    package: str
    success: bool
    method: str  # "tag-trigger-oidc" | "twine" | "skipped"
    version: str | None = None
    pypi_url: str | None = None
    message: str = ""
    artefacts: list[Path] = field(default_factory=list)

    def __str__(self) -> str:  # for human-friendly logs
        head = f"[{'OK' if self.success else 'FAIL'}] {self.package}"
        if self.version:
            head += f" v{self.version}"
        head += f" via {self.method}"
        if self.message:
            head += f" — {self.message}"
        return head


# ---------------------------------------------------------------------------
# Version detection


_VERSION_RE = re.compile(r"^version\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)


def detect_version(package_dir: str | Path) -> str:
    """Read ``[project].version`` from ``pyproject.toml``.

    Raises ValueError if not found.
    """
    pyproject = Path(package_dir) / "pyproject.toml"
    if not pyproject.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject}")
    text = pyproject.read_text(encoding="utf-8")
    m = _VERSION_RE.search(text)
    if not m:
        raise ValueError(f"could not find version = '...' in {pyproject}")
    return m.group(1)


def detect_package_name(package_dir: str | Path) -> str:
    """Read ``[project].name`` from ``pyproject.toml``."""
    pyproject = Path(package_dir) / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    m = re.search(r"^name\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    if not m:
        raise ValueError(f"could not find name = '...' in {pyproject}")
    return m.group(1)


# ---------------------------------------------------------------------------
# Method selection


def has_oidc_workflow(package_dir: str | Path) -> bool:
    """True if the repo has ``.github/workflows/publish-pypi.yml``."""
    return (Path(package_dir) / ".github" / "workflows" / "publish-pypi.yml").exists()


def is_published(package_name: str, version: str | None = None) -> bool:
    """Check if the package (or a specific version) exists on PyPI.

    Uses the public JSON API. Network-dependent; returns False on any error.
    """
    import json
    import urllib.request

    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
        if version is None:
            return True
        return version in data.get("releases", {})
    except Exception:
        return False


def select_method(package_dir: Path, requested: PublishMethod = "auto") -> str:
    """Decide which publish method to use.

    ``"auto"`` chooses ``"tag-trigger-oidc"`` if the workflow file exists,
    otherwise ``"twine"``.
    """
    if requested == "auto":
        return "tag-trigger-oidc" if has_oidc_workflow(package_dir) else "twine"
    return requested


# ---------------------------------------------------------------------------
# Method 1: tag-trigger-oidc


def publish_via_tag(
    package_dir: Path,
    version: str,
    *,
    dry_run: bool = True,
    remote: str = "origin",
) -> PublishResult:
    """Push a ``v<version>`` tag to fire the repo's GH Actions OIDC workflow.

    Assumes ``.github/workflows/publish-pypi.yml`` exists and a trusted
    publisher (or pending publisher) is configured on PyPI for this package.

    Idempotent: if the tag already exists locally, this is a no-op for the
    local tag; if it's already on the remote it is **not** force-pushed.
    """
    name = detect_package_name(package_dir)
    tag = f"v{version}"

    if dry_run:
        return PublishResult(
            package=name,
            success=True,
            method="tag-trigger-oidc",
            version=version,
            message=f"DRY RUN — would tag {tag} and push to {remote}",
        )

    git = ["git", "-C", str(package_dir)]

    # Local tag (idempotent: skip if already exists)
    existing = subprocess.run(
        git + ["tag", "--list", tag], capture_output=True, text=True
    )
    if existing.stdout.strip() != tag:
        r = subprocess.run(git + ["tag", tag], capture_output=True, text=True)
        if r.returncode != 0:
            return PublishResult(
                package=name,
                success=False,
                method="tag-trigger-oidc",
                version=version,
                message=f"git tag failed: {r.stderr.strip()}",
            )

    # Push
    r = subprocess.run(git + ["push", remote, tag], capture_output=True, text=True)
    if r.returncode != 0:
        return PublishResult(
            package=name,
            success=False,
            method="tag-trigger-oidc",
            version=version,
            message=f"git push failed: {r.stderr.strip()}",
        )

    return PublishResult(
        package=name,
        success=True,
        method="tag-trigger-oidc",
        version=version,
        pypi_url=f"https://pypi.org/p/{name}",
        message=f"pushed {tag}; watch GH Actions for the publish run",
    )


# ---------------------------------------------------------------------------
# Method 2: twine


def publish_via_twine(
    package_dir: Path,
    *,
    token: str | None = None,
    dry_run: bool = True,
    clean: bool = True,
    validate_classifiers_first: bool = True,
) -> PublishResult:
    """Build wheel + sdist and upload via ``twine``.

    Looks for the token in this order:
    1. ``token`` arg.
    2. ``PYPI_TOKEN`` env var.
    3. ``TWINE_PASSWORD`` env var.

    Build artefacts go to ``<package_dir>/dist/``. ``clean=True`` removes any
    existing ``dist/`` before building so stale wheels don't get re-uploaded.

    When ``validate_classifiers_first=True`` (default), invalid trove
    classifiers in pyproject.toml are caught locally before the build runs —
    PyPI returns 400 on upload for any unknown classifier, which is a common
    avoidable failure mode (real example: ``Topic :: Software Development ::
    Testing :: Benchmark`` looks plausible but isn't in the trove list).
    """
    from ._pypi_classifiers import validate_classifiers

    name = detect_package_name(package_dir)
    version = detect_version(package_dir)
    dist = package_dir / "dist"

    if validate_classifiers_first:
        bad = validate_classifiers(package_dir)
        if bad:
            return PublishResult(
                package=name,
                success=False,
                method="twine",
                version=version,
                message=f"invalid trove classifiers (PyPI would reject with 400): {bad}",
            )

    token = token or os.environ.get("PYPI_TOKEN") or os.environ.get("TWINE_PASSWORD")
    if not dry_run and not token:
        return PublishResult(
            package=name,
            success=False,
            method="twine",
            version=version,
            message="no token provided (set PYPI_TOKEN or pass token=...)",
        )

    # Idempotency: refuse to re-upload an already-published version.
    if is_published(name, version):
        return PublishResult(
            package=name,
            success=False,
            method="twine",
            version=version,
            message=f"v{version} is already on PyPI — bump pyproject.toml first",
        )

    if dry_run:
        return PublishResult(
            package=name,
            success=True,
            method="twine",
            version=version,
            message=f"DRY RUN — would build {package_dir}/dist/* and upload to PyPI",
        )

    if clean and dist.exists():
        shutil.rmtree(dist)

    # Build
    r = subprocess.run(
        [sys.executable, "-m", "build"],
        cwd=package_dir,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return PublishResult(
            package=name,
            success=False,
            method="twine",
            version=version,
            message=f"build failed: {r.stderr.strip().splitlines()[-1] if r.stderr else 'unknown'}",
        )

    artefacts = sorted(dist.glob("*"))
    if not artefacts:
        return PublishResult(
            package=name,
            success=False,
            method="twine",
            version=version,
            message="build produced no artefacts in dist/",
        )

    # Upload
    env = os.environ.copy()
    env["TWINE_USERNAME"] = "__token__"
    env["TWINE_PASSWORD"] = token  # type: ignore[assignment]
    r = subprocess.run(
        [sys.executable, "-m", "twine", "upload", *(str(a) for a in artefacts)],
        cwd=package_dir,
        capture_output=True,
        text=True,
        env=env,
    )
    if r.returncode != 0:
        return PublishResult(
            package=name,
            success=False,
            method="twine",
            version=version,
            message=f"twine upload failed: {r.stderr.strip().splitlines()[-1] if r.stderr else 'unknown'}",
            artefacts=artefacts,
        )

    return PublishResult(
        package=name,
        success=True,
        method="twine",
        version=version,
        pypi_url=f"https://pypi.org/project/{name}/{version}/",
        message="uploaded successfully",
        artefacts=artefacts,
    )


# ---------------------------------------------------------------------------
# Top-level dispatcher


def publish(
    package_dir: str | Path,
    *,
    version: str | None = None,
    method: PublishMethod = "auto",
    token: str | None = None,
    dry_run: bool = True,
    confirm: bool = False,
    skip_if_published: bool = True,
) -> PublishResult:
    """Publish a single package to PyPI.

    Parameters
    ----------
    package_dir : str | Path
        Path to a package's repo root (must contain pyproject.toml).
    version : str | None
        Version string, e.g. ``"0.1.0"``. Auto-detected from pyproject.toml
        when None.
    method : "auto" | "tag-trigger-oidc" | "twine"
        Publish method. ``"auto"`` prefers OIDC (the
        ``.github/workflows/publish-pypi.yml`` tag-trigger pipeline) when the
        workflow file exists; falls back to ``"twine"`` only if it doesn't.
    token : str | None
        PyPI API token for the ``twine`` method. Falls back to
        ``$PYPI_TOKEN`` / ``$TWINE_PASSWORD``. Ignored for OIDC.
    dry_run : bool
        Preview only, don't actually tag or upload.
    confirm : bool
        Convenience: if True, sets ``dry_run=False``.
    skip_if_published : bool
        If True (default), return early with ``method="skipped"`` and
        ``success=True`` when ``<name>==<version>`` is already on PyPI. This
        keeps batch runs idempotent and lets the GitHub-release/OIDC pipeline
        stay the source of truth.
    """
    if confirm:
        dry_run = False

    package_dir = Path(package_dir).expanduser().resolve()
    if not (package_dir / "pyproject.toml").exists():
        raise FileNotFoundError(f"no pyproject.toml at {package_dir}")

    name = detect_package_name(package_dir)
    version = version or detect_version(package_dir)

    # Idempotency: skip already-published versions (prioritize the GH release
    # pipeline as the canonical mechanism — twine reruns are a side-channel).
    if skip_if_published and is_published(name, version):
        return PublishResult(
            package=name,
            success=True,
            method="skipped",
            version=version,
            pypi_url=f"https://pypi.org/project/{name}/{version}/",
            message=f"v{version} already on PyPI — nothing to do",
        )

    method_chosen = select_method(package_dir, method)

    if method_chosen == "tag-trigger-oidc":
        return publish_via_tag(package_dir, version, dry_run=dry_run)
    if method_chosen == "twine":
        return publish_via_twine(package_dir, token=token, dry_run=dry_run)
    raise ValueError(f"unknown method: {method_chosen!r}")


# ---------------------------------------------------------------------------
# Batch operations


def publish_all(
    packages: Iterable[str | Path],
    *,
    method: PublishMethod = "auto",
    token: str | None = None,
    dry_run: bool = True,
    confirm: bool = False,
    skip_if_published: bool = True,
    stop_on_error: bool = False,
) -> list[PublishResult]:
    """Publish multiple packages; returns a list of PublishResult.

    Already-published versions are skipped (``method="skipped"``,
    ``success=True``) so the loop is idempotent — re-running it after a
    partial batch only retries the ones that still need work. The
    GitHub-release/OIDC pipeline stays the source of truth.

    For ecosystems with peer dependencies, callers should sort ``packages``
    in topological order (foundations first, dependents last). This module
    does not attempt automatic dep-graph resolution — see
    ``scitex_dev.ecosystem`` for that.
    """
    results: list[PublishResult] = []
    for pkg in packages:
        r = publish(
            pkg,
            method=method,
            token=token,
            dry_run=dry_run,
            confirm=confirm,
            skip_if_published=skip_if_published,
        )
        results.append(r)
        if stop_on_error and not r.success:
            break
    return results


# ---------------------------------------------------------------------------
# Trusted-publisher form values (helper, no side effects)


def trusted_publisher_form(
    package_name: str, github_owner: str = "ywatanabe1989"
) -> dict:
    """Return the five form values to register a pending publisher on PyPI.

    PyPI does not expose an API for trusted-publisher configuration; this is
    a helper for printing or copy-pasting into the form at
    https://pypi.org/manage/account/publishing/.
    """
    return {
        "PyPI Project Name": package_name,
        "Owner": github_owner,
        "Repository name": package_name,
        "Workflow name": "publish-pypi.yml",
        "Environment name": "pypi",
    }


__all__ = [
    "PublishMethod",
    "PublishResult",
    "detect_version",
    "detect_package_name",
    "has_oidc_workflow",
    "is_published",
    "select_method",
    "publish_via_tag",
    "publish_via_twine",
    "publish",
    "publish_all",
    "trusted_publisher_form",
]

# EOF
