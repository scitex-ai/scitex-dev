"""Quality audit subcommand: `scitex-dev quality audit-<subcmd>`."""

import subprocess
import sys
from pathlib import Path

from ._pyproject_lint import lint_pyproject
from ._release_publisher import publish_release
from ._rtd_onboard import onboard_rtd

SCRIPTS = Path(__file__).parent.parent.parent / "scripts" / "quality"


def audit_docs(projects_root: str | None = None):
    """Run doc-example auditor."""
    args = [sys.executable, str(SCRIPTS / "audit_doc_examples.py")]
    if projects_root:
        args += ["--projects-root", projects_root]
    return subprocess.call(args)


def audit_scope(projects_root: str | None = None):
    """Run test-scope auditor."""
    args = [sys.executable, str(SCRIPTS / "audit_test_scope.py")]
    if projects_root:
        args += ["--projects-root", projects_root]
    return subprocess.call(args)


def audit_lines():
    """Run line-limit auditor."""
    return subprocess.call([sys.executable, str(SCRIPTS / "audit_line_limits.py")])


def lint_pyproject_cli(repo_root: str | None = None, strict: bool = False) -> int:
    """Lint a single repo's pyproject.toml against the codified rules.

    Returns 0 if no findings; 1 if any HIGH/CRITICAL; 2 if MEDIUM/LOW only and
    --strict is set.
    """
    repo = Path(repo_root or ".").resolve()
    rep = lint_pyproject(repo)
    if not rep.findings:
        print(f"{rep.package}: clean")
        return 0
    print(f"{rep.package}  ({rep.pyproject})")
    for f in rep.findings:
        print(f"  {f.render()}")
    if rep.has_high:
        return 1
    return 2 if strict else 0


def rtd_onboard_cli(repo_root: str | None = None, dry_run: bool = False) -> int:
    """Scaffold a minimal Read the Docs setup. Idempotent."""
    repo = Path(repo_root or ".").resolve()
    rep = onboard_rtd(repo, dry_run=dry_run)
    print(rep.render())
    return 0 if not rep.failed else 1


def release_publish_cli(
    repo_root: str | None = None,
    version: str | None = None,
    notes: str | None = None,
    dry_run: bool = False,
) -> int:
    """Smart `git tag -> push -> gh release create` (per workflow trigger).

    Auto-detects whether the repo's publish-pypi.yml fires on
    ``release: published`` or ``push: tags`` and runs the right
    sequence. Idempotent: skips an existing tag or release.
    """
    repo = Path(repo_root or ".").resolve()
    if not version:
        # Default to pyproject.toml version if not specified.
        try:
            import tomllib  # type: ignore[import-not-found]
        except ImportError:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        with (repo / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
        version = (data.get("project") or {}).get("version")
    if not version:
        print(
            "error: --version required (and pyproject.toml has none)", file=sys.stderr
        )
        return 1
    rep = publish_release(repo, version, notes=notes, dry_run=dry_run)
    print(rep.render())
    return 0 if not rep.failed else 1


def audit_ecosystem(
    projects_root: str | None = None,
    out: str | None = None,
    categories: str = "umbrella,library,external-lib",
):
    """Run the ecosystem-wide static auditor."""
    args = [sys.executable, str(SCRIPTS / "audit_ecosystem.py"), "--quiet"]
    if projects_root:
        args += ["--projects-root", projects_root]
    if out:
        args += ["--out", out]
    if categories:
        args += ["--categories", categories]
    return subprocess.call(args)


def _main(argv=None):
    """Minimal argv dispatcher so `python -m scitex_dev._cli_quality <cmd>` works."""
    import argparse

    parser = argparse.ArgumentParser(prog="scitex_dev._cli_quality")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_docs = sub.add_parser("audit_docs", help="Run doc-example auditor")
    p_docs.add_argument("--projects-root", default=None)

    p_scope = sub.add_parser("audit_scope", help="Run test-scope auditor")
    p_scope.add_argument("--projects-root", default=None)

    sub.add_parser("audit_lines", help="Run line-limit auditor")

    args = parser.parse_args(argv)
    if args.cmd == "audit_docs":
        return audit_docs(projects_root=args.projects_root)
    if args.cmd == "audit_scope":
        return audit_scope(projects_root=args.projects_root)
    if args.cmd == "audit_lines":
        return audit_lines()
    parser.error(f"Unknown subcommand: {args.cmd}")


if __name__ == "__main__":
    sys.exit(_main())
