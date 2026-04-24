"""CLI convention auditor — optional feature (install via `scitex-dev[cli-audit]`).

Checks a package's Click command tree against the noun-verb convention in
`_skills/general/03_interface-cli.md`. Warn-only.

Resolution order per token:
    1. Custom dict — `<project>/.scitex/dev/cli-audit-dict.yaml`
    2. Custom dict — `~/.scitex/dev/cli-audit-dict.yaml`
    3. Bundled §1c catalog — `CATALOG` below
    4. Moby POS — vendored dictionary (transitive/intransitive distinction)
    5. `unknown` — warning, add to custom dict

`AVAILABLE` is True when the Moby data ships with the install. Optional
NLP backends may land under the `cli-audit` extra later.
"""

from __future__ import annotations

from importlib import resources

try:
    _MOBY_REF = resources.files(__name__).joinpath("data", "mobypos.txt.gz")
    AVAILABLE = _MOBY_REF.is_file()
except (ModuleNotFoundError, FileNotFoundError):
    AVAILABLE = False

__all__ = ["AVAILABLE", "audit_cli", "CATALOG"]

# §1c canonical catalog — shadows Moby for overloaded tokens (`list`, `start`).
CATALOG: dict[str, set[str]] = {
    # Nouns (domain categories)
    **{
        w: {"noun"}
        for w in [
            "package",
            "project",
            "module",
            "script",
            "example",
            "template",
            "manifest",
            "release",
            "config",
            "profile",
            "preset",
            "env-var",
            "skill",
            "doc",
            "docs",
            "readme",
            "changelog",
            "guideline",
            "dataset",
            "file",
            "path",
            "cache",
            "db",
            "index",
            "record",
            "bibentry",
            "figure",
            "table",
            "paper",
            "claim",
            "host",
            "machine",
            "remote",
            "tunnel",
            "container",
            "image",
            "server",
            "service",
            "process",
            "job",
            "task",
            "run",
            "ecosystem",
            "api",
            "mcp",
            "tool",
            "plugin",
            "hook",
            "command",
            "event",
            "log",
            "user",
            "account",
            "token",
            "key",
            "secret",
            "role",
            "session",
            "completion",
            "stats",
            "quality",
            # Common plurals (Moby POS marks most plurals with 'p' not 'N' — seed here)
            "skills",
            "packages",
            "projects",
            "jobs",
            "tasks",
            "runs",
            "hosts",
            "machines",
            "remotes",
            "tunnels",
            "containers",
            "images",
            "events",
            "logs",
            "figures",
            "tables",
            "papers",
            "bibentries",
            "claims",
            "datasets",
            "tools",
            "records",
            "files",
            "paths",
            "caches",
            "users",
            "accounts",
            "tokens",
            "keys",
            "secrets",
            "sessions",
            "commands",
            "examples",
            "templates",
            "manifests",
            "releases",
            "configs",
            "profiles",
            "presets",
            "env-vars",
            "docs",
            "modules",
            "scripts",
            "guidelines",
            "installation",
            "installations",
            # Domain-specific nouns (container backends, ecosystem jargon)
            "apptainer",
            "singularity",
            "docker",
            "podman",
            "sandbox",
            "backend",
            "backends",
            "sms",
            "template",
            "templates",
            "mount",
            "mounts",
            "snapshot",
            "snapshots",
            # Scientific dataset sources (neuro, chem, bio)
            "openneuro",
            "dandi",
            "physionet",
            "zenodo",
            "figshare",
            "openml",
            "moleculenet",
            "chembl",
            "clinicaltrials",
            "geo",
            "allen",
            "pubmed",
            "crossref",
            "openalex",
        ]
    },
    # Transitive verbs — need an object
    **{
        w: {"verb-t"}
        for w in [
            "list",
            "show",
            "get",
            "find",
            "search",
            "describe",
            "inspect",
            "diff",
            "tail",
            "create",
            "add",
            "init",
            "generate",
            "scaffold",
            "clone",
            "copy",
            "import",
            "register",
            "update",
            "edit",
            "rename",
            "move",
            "merge",
            "patch",
            "reset",
            "restore",
            "rollback",
            "delete",
            "remove",
            "purge",
            "clean",
            "archive",
            "revoke",
            "start",
            "stop",
            "restart",
            "pause",
            "resume",
            "enable",
            "disable",
            "install",
            "uninstall",
            "setup",
            "bootstrap",
            "exists",
            "exist",
            "build",
            "compile",
            "publish",
            "deploy",
            "tag",
            "ship",
            "load",
            "save",
            "read",
            "write",
            "fetch",
            "download",
            "upload",
            "export",
            "convert",
            "render",
            "parse",
            "validate",
            "check",
            "test",
            "lint",
            "format",
            "audit",
            "verify",
            "benchmark",
            "sync",
            "pull",
            "push",
            "commit",
            "stash",
            "apply",
            "reconcile",
            "send",
            "notify",
            "broadcast",
            "subscribe",
        ]
    },
    # Intransitive verbs — may be flat keepers per §1a
    **{w: {"verb-i"} for w in ["doctor", "repl", "shell"]},
    # Allowed flat-keeper exceptions
    "version": {"flat-keeper"},
}

FLAT_KEEPERS = {"doctor", "repl", "shell", "version"}


def audit_cli(package: str) -> int:
    """Audit a package's installed CLI; return exit code (always 0 — warn-only)."""
    if not AVAILABLE:
        import click

        click.echo(
            "scitex-dev[cli-audit] is not installed or data is missing. "
            "Install with: pip install 'scitex-dev[cli-audit]'",
            err=True,
        )
        return 2

    from ._audit import run_audit

    return run_audit(package)
