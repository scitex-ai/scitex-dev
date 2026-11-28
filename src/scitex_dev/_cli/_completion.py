#!/usr/bin/env python3
"""Shared CLI tab-completion helper for every scitex-* package.

Per `_skills/general/03_interface/02_cli/03_required-introspection-commands.md`
§1a, every scitex-* CLI MUST expose `install-shell-completion` and
`print-shell-completion` so users actually get `<TAB>` completion.

Usage from a downstream package's CLI module:

    from scitex_dev._cli._completion import attach_shell_completion

    @click.group(...)
    def cli():
        ...

    attach_shell_completion(cli, prog_name="scitex-io")
    # a package shipping a second console script for the same group:
    attach_shell_completion(cli, prog_name="scitex-agent-container",
                            aliases=("sac",))

That single call registers four leaves on `cli`:

  * `install-shell-completion --shell {bash,zsh,fish}`  (canonical)
  * `print-shell-completion   --shell {bash,zsh,fish}`  (canonical)
  * `install-tab-completion`   (hidden deprecated alias → install-shell-completion)
  * `completion`               (hidden deprecated alias → install-shell-completion)

Install contract (scitex-dev#1127):

  * It NEVER modifies a shell rc file (`~/.bashrc`, `~/.zshrc`, ...). On many
    machines the rc file is a symlink into a version-controlled dotfiles
    checkout, so appending to it dirties a tracked file on every host that
    installs a package. Earlier versions appended a `source` line per CLI.
  * It writes one package-owned drop-in file per console script, at the
    location the shell's completion framework already scans:

      bash  ${BASH_COMPLETION_USER_DIR:-${XDG_DATA_HOME:-~/.local/share}/bash-completion}/completions/<prog>
      zsh   ${XDG_DATA_HOME:-~/.local/share}/zsh/site-functions/_<prog>
      fish  ${XDG_CONFIG_HOME:-~/.config}/fish/completions/<prog>.fish

    bash-completion >= 2 loads the bash file lazily on the first `<TAB>`; fish
    loads its file automatically; zsh needs the directory on `fpath` before
    `compinit` (printed as a hint, never written).
  * It is idempotent: an unchanged script is not rewritten; writes are atomic.
  * It refuses to write when the target (or a directory on its way, resolved
    through symlinks) lies inside a git work tree.

The script is generated with this interpreter's Click against the registered
group; no console program is executed from `PATH`.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import click
from click.shell_completion import get_completion_class

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand

SHELLS = ("bash", "zsh", "fish")

__all__ = [
    "SHELLS",
    "CompletionInstall",
    "attach_shell_completion",
    "completion_dropin_path",
    "generate_completion_script",
    "install_completion",
    "legacy_rc_lines",
]


def _env_var(prog_name: str) -> str:
    """Click's autocompletion env var format: `_<UPPER_PROG>_COMPLETE`."""
    return "_" + prog_name.upper().replace("-", "_") + "_COMPLETE"


def _legacy_marker(prog_name: str) -> str:
    """Trailing comment earlier versions appended to rc lines."""
    return f"# {prog_name} tab completion"


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def _xdg_data_home() -> Path:
    raw = os.environ.get("XDG_DATA_HOME")
    return Path(raw) if raw else _home() / ".local" / "share"


def _xdg_config_home() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME")
    return Path(raw) if raw else _home() / ".config"


def completion_dropin_path(shell: str, prog_name: str) -> Path:
    """Where `install-shell-completion` writes `prog_name`'s script for `shell`.

    These are the per-user directories each shell's completion framework scans
    on its own, so no rc file has to name them.
    """
    if shell == "bash":
        # bash-completion 2.x: BASH_COMPLETION_USER_DIR may list several
        # colon-separated roots; the first one is the user's primary.
        user_dirs = os.environ.get("BASH_COMPLETION_USER_DIR", "")
        first = user_dirs.split(":")[0] if user_dirs else ""
        root = Path(first) if first else _xdg_data_home() / "bash-completion"
        return root / "completions" / prog_name
    if shell == "zsh":
        return _xdg_data_home() / "zsh" / "site-functions" / f"_{prog_name}"
    if shell == "fish":
        return _xdg_config_home() / "fish" / "completions" / f"{prog_name}.fish"
    raise click.ClickException(f"Unsupported completion shell: {shell}.")


def generate_completion_script(
    shell: str, prog_name: str, command: click.Command
) -> str:
    """Generate with this interpreter's Click, without executing PATH entries."""
    completion_class = get_completion_class(shell)
    if completion_class is None:
        raise click.ClickException(f"Unsupported completion shell: {shell}.")
    script = (
        completion_class(command, {}, prog_name, _env_var(prog_name)).source().strip()
    )
    if not script:
        raise click.ClickException(
            f"Failed to generate {shell} completion script for {prog_name}."
        )
    return script + "\n"


def _enclosing_git_work_tree(path: Path) -> Path | None:
    """The nearest ancestor of `path` (inclusive) holding a `.git` entry."""
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _refuse_if_versioned(target: Path) -> None:
    """Refuse to write a completion file into version-controlled territory.

    Two ways a per-user path can land in a git work tree, both resolved through
    symlinks: a directory on the way is (or links into) a checkout, e.g. a
    dotfiles repo that manages `~/.local/share`; or the target itself is a
    symlink a dotfiles manager placed there. Replacing either would dirty or
    clobber a tracked file — the defect this helper exists to stop.
    """
    places = [target.parent.resolve()]
    if target.is_symlink():
        places.append(target.resolve().parent)
    for place in places:
        repo = _enclosing_git_work_tree(place)
        if repo is not None:
            raise click.ClickException(
                f"refusing to write {target}: it resolves into the git work "
                f"tree {repo}. Writing there would modify a version-controlled "
                f"checkout. Point the shell at another directory (e.g. set "
                f"XDG_DATA_HOME / BASH_COMPLETION_USER_DIR), or save the "
                f"script yourself with `print-shell-completion`."
            )


def _atomic_write(path: Path, content: str) -> None:
    """Write `content` to `path` via a same-directory temp file and rename.

    `os.replace` swaps the directory entry, so a pre-existing symlink at
    `path` is replaced rather than written through.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


@dataclass(frozen=True)
class CompletionInstall:
    """Outcome of installing one console script's completion file."""

    prog_name: str
    path: Path
    status: str  # "written" | "unchanged" | "would-write"


def install_completion(
    command: click.Command,
    shell: str,
    prog_names: tuple[str, ...] | list[str],
    *,
    dry_run: bool = False,
) -> list[CompletionInstall]:
    """Write one drop-in completion file per name in `prog_names`.

    Never touches a shell rc file. Raises `click.ClickException` (before any
    write) when a target would land inside a git work tree.
    """
    plans = []
    for prog_name in prog_names:
        target = completion_dropin_path(shell, prog_name)
        _refuse_if_versioned(target)
        plans.append((prog_name, target))

    outcomes = []
    for prog_name, target in plans:
        if dry_run:
            outcomes.append(CompletionInstall(prog_name, target, "would-write"))
            continue
        script = generate_completion_script(shell, prog_name, command)
        current = (
            target.read_text(encoding="utf-8")
            if target.is_file() and not target.is_symlink()
            else None
        )
        if current == script:
            outcomes.append(CompletionInstall(prog_name, target, "unchanged"))
            continue
        _atomic_write(target, script)
        outcomes.append(CompletionInstall(prog_name, target, "written"))
    return outcomes


def legacy_rc_lines(shell: str, prog_name: str) -> list[tuple[Path, str]]:
    """Lines an earlier version of this helper appended to the rc file.

    Read-only: the caller reports them so the user (or the owner of a dotfiles
    repo) can delete them; this module never edits an rc file.
    """
    rc_name = {"bash": ".bashrc", "zsh": ".zshrc"}.get(shell)
    if rc_name is None:
        return []
    rc = _home() / rc_name
    try:
        text = rc.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    marker = _legacy_marker(prog_name)
    lines = text.splitlines()
    found = []
    for index, line in enumerate(lines):
        if not line.rstrip().endswith(marker):
            continue
        found.append((rc, line))
        # Some installers wrote the marker as its own comment line above the
        # `eval` line; report that line too so the user deletes both.
        if line.strip() == marker and index + 1 < len(lines):
            found.append((rc, lines[index + 1]))
    return found


def _activation_hint(shell: str, outcomes: list[CompletionInstall]) -> str:
    if shell == "bash":
        return (
            "bash-completion (>= 2) loads it on the first <TAB> in a new "
            "shell; no rc edit needed."
        )
    if shell == "zsh":
        directory = outcomes[0].path.parent if outcomes else ""
        return (
            f"zsh loads it from fpath: if {directory} is not on your fpath "
            f"yet, add `fpath=({directory} $fpath)` before `compinit` in "
            f"your zsh config (this command never edits it)."
        )
    return "fish loads it automatically in a new shell."


def attach_shell_completion(
    main_group, *, prog_name: str, aliases: tuple[str, ...] = ()
) -> None:
    """Register the 4 shell-completion leaves on `main_group`.

    `aliases` names further console scripts bound to the same group (Click
    keys completion on argv[0], so each name gets its own file).
    """
    prog_names = (prog_name, *aliases)

    @main_group.command(
        "print-shell-completion",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Print the click-generated completion script to stdout.",
            examples=(
                Example(
                    "{prog} print-shell-completion --shell bash",
                    "Print the bash script.",
                ),
                Example(
                    "{prog} print-shell-completion --shell zsh",
                    "Print the zsh script.",
                ),
                Example(
                    'eval "$({prog} print-shell-completion --shell bash)"',
                    "Activate it in the current shell.",
                ),
            ),
        ),
    )
    @click.option(
        "--shell",
        type=click.Choice(list(SHELLS)),
        default="bash",
        help="Target shell. Default: bash.",
    )
    def print_shell_completion(shell):
        click.echo(generate_completion_script(shell, prog_name, main_group), nl=False)

    @main_group.command(
        "install-shell-completion",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Write TAB-completion drop-in files; never edits shell rc files.",
            description=(
                "Writes one file per console script into the per-user "
                "directory the shell's completion framework scans "
                "(bash: ~/.local/share/bash-completion/completions/). "
                "Idempotent; refuses to write into a git work tree.",
            ),
            examples=(
                Example(
                    "{prog} install-shell-completion",
                    "Install the bash drop-in.",
                ),
                Example(
                    "{prog} install-shell-completion --shell zsh",
                    "Install the zsh drop-in (fpath site-functions).",
                ),
                Example(
                    "{prog} install-shell-completion --dry-run",
                    "Preview only.",
                ),
            ),
        ),
    )
    @click.option(
        "--shell",
        type=click.Choice(list(SHELLS)),
        default="bash",
        help="Target shell. Default: bash.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the target drop-in path(s) without writing.",
    )
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
    def install_shell_completion(shell, dry_run, yes):
        del yes  # accepted for §2 compliance; install never prompts
        outcomes = install_completion(main_group, shell, prog_names, dry_run=dry_run)
        for outcome in outcomes:
            label = {
                "would-write": "Would write",
                "written": "Wrote",
                "unchanged": "Up to date",
            }[outcome.status]
            click.echo(f"{label}: {outcome.path}")
        for name in prog_names:
            for rc, line in legacy_rc_lines(shell, name):
                click.echo(
                    f"note: {rc} still carries a line an older installer "
                    f"appended; it is no longer needed and can be deleted:\n"
                    f"  {line}",
                    err=True,
                )
        if not dry_run:
            click.echo(_activation_hint(shell, outcomes))

    @main_group.command(
        "install-tab-completion",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def install_tab_completion_deprecated(ctx):
        """(deprecated) Renamed to `install-shell-completion`."""
        click.echo(
            f"error: `{prog_name} install-tab-completion` was renamed to "
            f"`{prog_name} install-shell-completion`.\n"
            f"Re-run with: {prog_name} install-shell-completion",
            err=True,
        )
        ctx.exit(2)

    @main_group.command(
        "completion",
        hidden=True,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    @click.pass_context
    def completion_deprecated(ctx):
        """(deprecated) Renamed to `install-shell-completion`."""
        click.echo(
            f"error: `{prog_name} completion` was renamed to "
            f"`{prog_name} install-shell-completion`.\n"
            f"Re-run with: {prog_name} install-shell-completion",
            err=True,
        )
        ctx.exit(2)


# ----- Backwards compat for scitex-dev's own _root.py call site ----------
# The legacy entry point `register_completion_command(main_group)` is kept
# so scitex-dev's existing import doesn't break during the rollout.


def register_completion_command(main_group):
    """(legacy) Use `attach_shell_completion(main_group, prog_name=...)`."""
    attach_shell_completion(main_group, prog_name="scitex-dev")
