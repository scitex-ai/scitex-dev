#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem ``system-deps`` -- aggregate every leaf's declared system deps.

Each scitex leaf declares its SYSTEM dependencies via a
``scitex_dev.system_deps`` entry-point provider; this command aggregates them
(deduped by name) so container builds install ONE federated set instead of
hardcoding/duplicating install lists across container definitions.

Two install kinds share the one group:

* ``kind="apt"``: distro packages. apt needs root, so ``install`` is
  BUILD-TIME only (run in a container ``%post`` / Dockerfile). ``list``
  emits apt names for piping, e.g.::

    apt-get install -y --no-install-recommends \\
        $(scitex-dev ecosystem system-deps list)

  ``list`` emits ``kind="apt"`` names ONLY, so a script-kind entry never
  lands on an apt command line.
* ``kind="script"``: user-space ``curl | bash`` installers (no root; run
  at HOST-CONFIGURE time). ``install-script --provider <leaf>`` previews
  (dry-run) or runs the pinned installer, then proves the install with
  the declaration's ``verify_command``.

``validate-superset`` gates a container cutover: it proves the federated
apt set is a superset of a recipe's current hardcoded apt list, so
nothing is silently dropped when those hardcoded blocks are deleted.
"""

from __future__ import annotations

import click

from ...._ecosystem.click_compat import deprecated_alias
from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup

from ...._core.streams import render_rich


def _select(provider, *, kind=None):
    """Discover + optionally filter to one provider and/or install kind."""
    from ....system_deps import discover_system_deps

    deps = discover_system_deps()
    if provider:
        deps = [d for d in deps if d.provider == provider]
    if kind is not None:
        deps = [d for d in deps if d.kind == kind]
    return deps


def _do_install(deps, *, dry_run: bool) -> int:
    """apt-get install the aggregated APT set (BUILD-time; needs root).

    ``dry_run`` previews the exact apt commands without running them; it is the
    default when ``--yes`` is omitted (§2 mutating-verb convention).

    Script-kind deps never reach here: ``system_deps_install`` filters to
    ``kind="apt"`` before calling, and ``_select`` is filtered the same way
    by ``list`` -- but a direct caller passing a mixed set is refused
    loudly rather than silently apt-installing a tool name.
    """
    import os
    import subprocess

    script = sorted({d.package for d in deps if d.kind != "apt"})
    if script:
        click.echo(
            "ERROR: install handles kind='apt' only; script-kind dep(s) "
            f"{', '.join(script)} need `install-script --provider ...` "
            "(user-space curl|bash installer, host-configure time, no root).",
            err=True,
        )
        return 1
    if not deps:
        click.echo("No system deps declared by any provider; nothing to install.")
        return 0

    repos = sorted({d.apt_repo for d in deps if d.apt_repo})
    packages = [d.package for d in deps]

    if dry_run:
        for repo in repos:
            click.echo(f"+ add-apt-repository -y {repo}")
        click.echo("+ apt-get update")
        click.echo(f"+ apt-get install -y --no-install-recommends {' '.join(packages)}")
        click.echo("(dry-run — pass --yes to execute; BUILD-time / root only)")
        return 0

    if hasattr(os, "geteuid") and os.geteuid() != 0:
        click.echo(
            "ERROR: install --yes needs root and runs at IMAGE-BUILD time only "
            "(agents are rootless --userns). Use it inside a container %post / "
            "Dockerfile, or pipe `system-deps list` into apt-get there.",
            err=True,
        )
        return 1

    for repo in repos:
        click.echo(f"+ add-apt-repository -y {repo}")
        if subprocess.run(["add-apt-repository", "-y", repo]).returncode != 0:
            click.echo(f"ERROR: add-apt-repository failed for {repo}", err=True)
            return 1
    if subprocess.run(["apt-get", "update"]).returncode != 0:
        click.echo("ERROR: apt-get update failed", err=True)
        return 1
    click.echo(f"+ apt-get install -y --no-install-recommends {' '.join(packages)}")
    rc = subprocess.run(
        ["apt-get", "install", "-y", "--no-install-recommends", *packages]
    ).returncode
    if rc != 0:
        click.echo("ERROR: apt-get install failed", err=True)
        return 1
    return 0


def _render(deps) -> None:
    """Human-readable table of the aggregated declarations (both kinds)."""
    from rich.table import Table

    if not deps:
        render_rich(
            "[yellow]No system deps declared by any provider.[/yellow]", __name__
        )
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("package")
    table.add_column("kind")
    table.add_column("provider")
    table.add_column("purpose")
    table.add_column("source")
    for dep in deps:
        source = (
            dep.apt_repo or "-"
            if dep.kind == "apt"
            else (dep.install_url or "-")
        )
        table.add_row(dep.package, dep.kind, dep.provider, dep.purpose, source)
    render_rich(table, __name__)
    render_rich(
        f"[bold]{len(deps)}[/bold] system dep(s) across "
        f"{len({d.provider for d in deps})} provider(s).",
        __name__,
    )


def _emit_json(deps) -> None:
    import json as _json

    click.echo(
        _json.dumps(
            [
                {
                    "package": d.package,
                    "kind": d.kind,
                    "purpose": d.purpose,
                    "provider": d.provider,
                    "apt_repo": d.apt_repo,
                    "install_url": d.install_url,
                    "install_args": list(d.install_args),
                    "verify_command": d.verify_command,
                }
                for d in deps
            ],
            indent=2,
        )
    )


def _script_shell(dep) -> str:
    """Render the exact ``curl | bash`` command for one script-kind dep."""
    args = " ".join(["bash", "-s", "--", *dep.install_args]).rstrip()
    return f"curl -fsSL {dep.install_url} | {args}"


def _do_install_script(deps, *, dry_run: bool) -> int:
    """Run the pinned ``curl | bash`` installer for script-kind deps.

    User-space: no root involved, safe on a live host at configure time.
    Each dep is proven afterwards with its own ``verify_command`` --
    observation is the only accepted proof an install took.
    ``dry_run`` previews the exact shell commands; default when ``--yes``
    is omitted (§2 mutating-verb convention).
    """
    import subprocess

    if not deps:
        click.echo("No script-kind system deps selected; nothing to install.")
        return 0
    rc = 0
    for dep in deps:
        cmd = _script_shell(dep)
        if dry_run:
            click.echo(f"+ {cmd}")
            if dep.verify_command:
                click.echo(f"+ {dep.verify_command}  (verify)")
            click.echo("(dry-run — pass --yes to execute; user-space, no root)")
            continue
        click.echo(f"+ {cmd}")
        proc = subprocess.run(
            ["bash", "-c", f"curl -fsSL {dep.install_url} | bash -s -- {' '.join(dep.install_args)}".rstrip()],
        )
        if proc.returncode != 0:
            click.echo(f"ERROR: installer failed for {dep.package!r}", err=True)
            rc = 1
            continue
        if dep.verify_command:
            click.echo(f"+ {dep.verify_command}  (verify)")
            verify = subprocess.run(["bash", "-c", dep.verify_command])
            if verify.returncode != 0:
                click.echo(
                    f"ERROR: installed {dep.package!r} but the verify "
                    f"command failed: {dep.verify_command!r}",
                    err=True,
                )
                rc = 1
                continue
        click.echo(f"ok: {dep.package}")
    return rc


def _read_baseline(path):
    """Apt names from a baseline file (one per line; ``#`` comments + blanks skipped)."""
    names = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            name = line.split("#", 1)[0].strip()
            if name:
                names.add(name)
    return names


def _superset_delta(aggregated, baseline):
    """Return ``(missing, added)`` sorted lists for a superset check.

    ``missing`` = baseline packages no provider declares (a RED result: they
    would be dropped at cutover). ``added`` = packages providers declare beyond
    the baseline (the image gains them; informational).
    """
    missing = sorted(set(baseline) - set(aggregated))
    added = sorted(set(aggregated) - set(baseline))
    return missing, added


def register(ecosystem):
    @ecosystem.group(
        "system-deps",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Aggregate the ecosystem's declared system dependencies.",
            description=(
                "Walks every `scitex_dev.system_deps` provider and "
                "dedups by name. With no subcommand, "
                "prints a human table (both install kinds); `list` is "
                "pipe-friendly (apt names only); "
                "`install` applies the apt set at image-build time; "
                "`install-script` runs pinned curl|bash installers at "
                "host-configure time. "
                "Declarations live in each leaf (scitex_dev.system_deps "
                "entry point). APT INSTALL IS BUILD-TIME ONLY (apt needs "
                "root; agents run rootless --userns).",
            ),
            examples=(
                Example("{prog} ecosystem system-deps", "Human table."),
                Example("{prog} ecosystem system-deps list", "apt names, one per line."),
                Example(
                    "{prog} ecosystem system-deps install-script --provider scitex-agent-container",
                    "Preview the Hermes installer.",
                ),
            ),
        ),
    )
    @click.pass_context
    def system_deps(ctx):
        if ctx.invoked_subcommand is None:
            _render(_select(None))

    @system_deps.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Print the aggregated apt package names, one per line (pipe-friendly).",
            examples=(
                Example("{prog} ecosystem system-deps list", "Names, one per line."),
                Example(
                    "apt-get install -y $({prog} ecosystem system-deps list)",
                    "Pipe into apt-get.",
                ),
            ),
        ),
    )
    @click.option(
        "--provider",
        default=None,
        help="Filter to one declaring package (e.g. scitex-writer).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    def system_deps_list(provider, as_json):
        # `list` feeds `apt-get install` on a pipe -- apt names ONLY, so a
        # script-kind package name never lands on an apt command line.
        deps = _select(provider, kind="apt")
        if as_json:
            _emit_json(deps)
            return 0
        for dep in deps:
            click.echo(dep.package)
        return 0

    @system_deps.command(
        "install",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="apt-get install the aggregated set (BUILD-time; needs root).",
            description=("Mutating verb: previews (dry-run) unless --yes is given.",),
            examples=(
                Example("{prog} ecosystem system-deps install", "Preview."),
                Example("{prog} ecosystem system-deps install --yes", "Execute (root)."),
            ),
        ),
    )
    @click.option(
        "--provider",
        default=None,
        help="Filter to one declaring package (e.g. scitex-writer).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the apt commands without running them (default when --yes "
        "is omitted).",
    )
    @click.option(
        "--yes",
        "-y",
        "yes",
        is_flag=True,
        help="Actually run apt-get (BUILD-time; needs root).",
    )
    def system_deps_install(provider, dry_run, yes):
        # `install` is the apt surface -- a script-kind dep has no apt
        # name, so it is filtered here and refused loudly inside
        # `_do_install` if one ever slips through.
        return _do_install(
            _select(provider, kind="apt"), dry_run=dry_run or not yes
        )

    @system_deps.command(
        "install-script",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Run pinned curl|bash installers (HOST-configure time; no root).",
            description=(
                "Mutating verb: previews (dry-run) unless --yes is given. "
                "Each script-kind dep runs its declared installer, then is "
                "proven with its own verify_command.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem system-deps install-script --provider scitex-agent-container",
                    "Preview the Hermes installer.",
                ),
                Example(
                    "{prog} ecosystem system-deps install-script --provider scitex-agent-container --yes",
                    "Install Hermes on this host.",
                ),
            ),
        ),
    )
    @click.option(
        "--provider",
        default=None,
        help="Filter to one declaring package (e.g. scitex-agent-container).",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the installer commands without running them (default when --yes "
        "is omitted).",
    )
    @click.option(
        "--yes",
        "-y",
        "yes",
        is_flag=True,
        help="Actually run the installers (user-space; no root needed).",
    )
    def system_deps_install_script(provider, dry_run, yes):
        return _do_install_script(
            _select(provider, kind="script"), dry_run=dry_run or not yes
        )

    @system_deps.command(
        "validate-superset",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Gate a container cutover against a recipe baseline superset.",
            description=(
                "Run in the container BUILD env (where every leaf "
                "provider is installed) BEFORE deleting a recipe's "
                "hardcoded apt blocks — it proves nothing is silently "
                "dropped. Exit 0 = GREEN (superset, safe to drop the "
                "blocks); exit 1 = RED (a baseline package is declared "
                "by no provider). In a venv without the providers the "
                "federated set is empty, so a real baseline correctly "
                "reports RED.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem system-deps validate-superset --baseline recipe-apt.txt",
                    "Check against a baseline file.",
                ),
                Example(
                    "{prog} ecosystem system-deps validate-superset --baseline r.txt --json",
                    "Structured JSON verdict.",
                ),
            ),
        ),
    )
    @click.option(
        "--baseline",
        required=True,
        type=click.Path(exists=True, dir_okay=False),
        help="File of a recipe's current hardcoded apt names (one per line; "
        "# comments ok).",
    )
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit the verdict + delta as JSON."
    )
    @click.pass_context
    def system_deps_validate_superset(ctx, baseline, as_json):
        import json as _json

        # validate-superset gates a container apt cutover -- apt names
        # only, so a script-kind tool name never counts as coverage.
        aggregated = {dep.package for dep in _select(None, kind="apt")}
        baseline_set = _read_baseline(baseline)
        missing, added = _superset_delta(aggregated, baseline_set)

        if as_json:
            click.echo(
                _json.dumps(
                    {
                        "verdict": "red" if missing else "green",
                        "aggregated_count": len(aggregated),
                        "baseline_count": len(baseline_set),
                        "missing": missing,
                        "added": added,
                    },
                    indent=2,
                )
            )
            ctx.exit(1 if missing else 0)

        click.echo(
            f"aggregated (federated): {len(aggregated)}   "
            f"baseline (recipe): {len(baseline_set)}"
        )
        for pkg in added:
            click.echo(f"  + {pkg}  (added by providers, OK)")
        for pkg in missing:
            click.echo(f"  ! {pkg}  (in baseline, declared by NO provider)")
        if missing:
            click.echo(
                "RED: federated set is NOT a superset — do NOT drop the hardcoded "
                "blocks until every missing package is declared by a provider."
            )
            ctx.exit(1)
        click.echo(
            "GREEN: federated set ⊇ baseline — safe to drop the hardcoded blocks."
        )
        ctx.exit(0)

    # `check-superset` → `validate-superset` rename (§1f: `check` is a
    # non-canonical synonym for the ecosystem-wide `validate` verb).
    deprecated_alias(
        system_deps,
        "check-superset",
        target="validate-superset",
        remove_in="0.32",
        phase="warn",
    )
