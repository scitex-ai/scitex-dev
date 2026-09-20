"""Run a Python script after linting it.

Core function used by the `scitex-dev linter run-python` subcommand.
"""

import os
import subprocess
import sys

import scitex_logging as slogging

from .checker import lint_file
from .formatter import format_issue, format_summary
from .rules import SEVERITY_ORDER

log = slogging.getLogger(__name__)


def _is_git_root() -> bool:
    """Check if the current working directory is a git repository root."""
    return os.path.isdir(os.path.join(os.getcwd(), ".git"))


def run_script(filepath: str, strict: bool = False, script_args: list = None) -> int:
    """Lint a script then execute it.

    Returns the subprocess return code, or 2 if strict mode blocks execution.
    """
    if script_args is None:
        script_args = []

    # Check if running from git root
    use_color = sys.stderr.isatty()
    if not _is_git_root():
        hint = "\033[94mInfo\033[0m" if use_color else "Info"
        log.warning(
            f"{hint}: not running from a git root directory (cwd: {os.getcwd()})",
        )

    # Lint
    issues = lint_file(filepath)

    has_errors = any(i.rule.severity == "error" for i in issues)
    has_warnings = any(
        SEVERITY_ORDER[i.rule.severity] >= SEVERITY_ORDER["warning"] for i in issues
    )

    if issues:
        header = "\033[1mSciTeX Lint\033[0m" if use_color else "SciTeX Lint"
        log.warning(f"\n{header}\n")

        for issue in issues:
            log.warning(format_issue(issue, filepath, color=use_color))
        log.warning(format_summary(issues, filepath, color=use_color))
        log.warning()

    if strict and has_errors:
        msg = "\033[91mAborted\033[0m" if use_color else "Aborted"
        log.error(f"{msg}: errors found (--strict mode)\n")
        return 2

    if not has_errors and not has_warnings:
        ok = "\033[92mOK\033[0m" if use_color else "OK"
        log.success(f"{ok} {filepath}")

    # Execute
    sep = "\u2500" * 60
    if use_color:
        log.warning(f"\n\033[90m{sep}\033[0m")
    else:
        log.warning(f"\n{sep}")

    cmd = [sys.executable, filepath] + script_args
    result = subprocess.run(cmd)
    return result.returncode
