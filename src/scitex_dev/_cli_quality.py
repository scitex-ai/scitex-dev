"""Quality audit subcommand: `scitex-dev quality audit-<subcmd>`."""

import subprocess
import sys
from pathlib import Path

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
