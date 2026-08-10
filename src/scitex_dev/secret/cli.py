#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The `<pkg> dev secret …` command group, mountable by ANY leaf package.

PUBLIC on purpose, unlike the rest of the CLI. §13 says every package mounts
its self-maintenance surfaces under one ``dev`` group; this module is how a
leaf gets the credential half of that surface without reimplementing it:

    from scitex_dev.secret.cli import register_secret_group

    @main.group("dev")
    def dev() -> None:
        ...

    register_secret_group(dev, pkg="hub")

``scitex-hub dev secret list`` then operates on ``~/.scitex/hub/secret`` with
the same verbs, the same flags and the same failure messages as every other
package, because it is the same code — not a copy that drifts.

WHY ONE IMPLEMENTATION AND NOT A DOCUMENTED CONVENTION
------------------------------------------------------
A convention is followed by whoever read it. Measured across this ecosystem,
counting adoption of a convention that only existed as prose returned zero, and
two agents independently concluded the rule did not exist. A shared registrar
cannot be half-adopted: a leaf either calls it and gets the whole surface, or
does not and visibly has no `secret` group at all.

WHY `pkg` IS A PARAMETER
------------------------
It is the DEFAULT for ``--pkg``, so a leaf's own store is what its own CLI
touches without repeating the flag. ``--pkg`` remains available because
scitex-dev, as the SSOT, has to be able to inspect any package's store.

ACL LIVES IN THE RECIPIENT, NOT IN CODE
---------------------------------------
Who may read a store is decided by which GPG key it is encrypted to, per
store. There is no per-package branch anywhere in this module, and none is
needed in a consuming web application either: a process either holds the key
or it does not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup
from ..scope import Scope
from ._context import SecretContext, name_reservation_error
from ._store import OK, SecretStore


def _reject_reserved(name: str) -> None:
    """Refuse a name the owner layout claims, at the point of entry."""
    reason = name_reservation_error(name)
    if reason is not None:
        raise click.ClickException(reason)


def _root(app: str) -> Path:
    """The store these commands operate on.

    A terminal is a STANDALONE context by construction — one OS account, no
    logged-in web user — so no owner dimension is passed. Managing another
    user's or a group's store from the command line is a separate surface with
    its own authorisation question; it is deliberately not reachable by
    omitting a flag here.
    """
    return SecretContext(app=app, scope=Scope.standalone()).secret_root()

#: What ``--pkg`` defaults to when a caller does not say. scitex-dev's own
#: store; a leaf passes its own short name to ``register_secret_group``.
DEFAULT_PKG = "dev"


def _read_passphrase(passphrase_file: str) -> str:
    """Read a passphrase from a file, never from argv.

    CLI doctrine §2 forbids interactive prompts, so a value must be accepted as
    an option to stay scriptable. A passphrase must never appear in argv, which
    ``ps`` exposes to every user on the host. Both hold at once when the option
    carries a REFERENCE: ``--passphrase-file PATH`` is an ordinary option whose
    value is a path, and the secret is read from that file.
    """
    path = Path(passphrase_file).expanduser()
    if not path.is_file():
        raise click.ClickException(
            f"no passphrase file at {path}. Write the passphrase to a file with "
            "mode 600 and pass its PATH — the passphrase itself must never appear "
            "on a command line, where `ps` exposes it to every user on the host."
        )
    return path.read_text(encoding="utf-8").rstrip("\n")


def _emit(result, as_json: bool = False) -> None:
    """Print a result and exit non-zero on failure.

    The DETAIL always goes to stderr and the VALUE always to stdout, so a
    consumer doing ``KEY=$(… secret show name)`` can never capture an error
    message as the secret. That is the decrypt.sh defect — a 61-byte ANSI error
    string ingested as a password — closed at the CLI boundary too, not only
    inside the library.
    """
    if as_json:
        payload = {
            "code": result.code,
            "ok": result.code == OK,
            "detail": result.detail,
            "name": result.name,
            "names": list(result.names),
        }
        if result.value is not None:
            payload["value"] = result.value
        click.echo(json.dumps(payload, ensure_ascii=False))
        if result.code != OK:
            raise SystemExit(1)
        return

    if result.code == OK and result.value is not None:
        click.echo(result.value, nl=False)
        click.echo(result.detail, err=True)
        return
    click.echo(result.detail, err=True)
    for name in result.names:
        click.echo(name)
    if result.code != OK:
        raise SystemExit(1)


def _dry_run(action: str) -> None:
    click.echo(f"DRY RUN — would {action}. Nothing was changed.", err=True)


def register_secret_group(parent: click.Group, *, pkg: str = DEFAULT_PKG) -> click.Group:
    """Mount ``secret`` on *parent* (a package's ``dev`` group).

    ``pkg`` becomes the default for ``--pkg``, i.e. which store the commands
    operate on. Returns the group so a caller can add package-specific verbs.
    """

    @parent.group(
        "secret",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="GPG-backed credential store (pass-compatible layout).",
            description=(
                "Stores one gpg-encrypted file per secret under "
                f"~/.scitex/{pkg}/secret, in the layout `pass` reads, so either "
                "tool operates on the same store. Values never appear in argv. "
                "Decryption requires the private key, so `show` only works "
                "where that key lives."
            ),
            examples=(
                Example("{prog} dev secret init --recipient you@example.com",
                        "Create the store."),
                Example("{prog} dev secret set api/token --yes",
                        "Store a value a provider issued, from stdin."),
                Example("{prog} dev secret show api/token",
                        "Print the secret to stdout."),
                Example("{prog} dev secret create-backup --dest ~/b.gpg "
                        "--passphrase-file ~/.pp",
                        "Archive the store AND the private key."),
            ),
        ),
    )
    @click.pass_context
    def secret(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    pkg_option = click.option(
        "--pkg", default=pkg, show_default=True,
        help="Which package's store to operate on (~/.scitex/<pkg>/secret).",
    )
    dry_run_option = click.option(
        "--dry-run", is_flag=True, help="Report what would happen; change nothing.",
    )
    yes_option = click.option(
        "--yes", "-y", is_flag=True,
        help="Confirm an action that would overwrite existing data.",
    )
    json_option = click.option(
        "--json", "as_json", is_flag=True, help="Emit a machine-readable JSON object.",
    )

    @secret.command(
        "init", cls=SpecCommand,
        help_spec=CliHelp(
            summary="Create the store for a recipient.",
            description=(
                "The recipient IS the access-control decision: whoever holds "
                "that private key can read this store, and nobody else can. "
                "Per-package stores with different recipients is how packages "
                "are isolated from each other."
            ),
            examples=(
                Example("{prog} dev secret init --recipient you@example.com",
                        "Create the store encrypted to that key."),
                Example("{prog} dev secret init --recipient you@example.com --dry-run",
                        "Show where it would be created."),
            ),
        ),
    )
    @click.option("--recipient", required=True,
                  help="GPG key id or uid that will be able to decrypt.")
    @pkg_option
    @dry_run_option
    @yes_option
    def init_cmd(recipient: str, pkg: str, dry_run: bool, yes: bool) -> None:
        root = _root(pkg)
        if dry_run:
            _dry_run(f"create a store at {root} encrypted to {recipient}")
            return
        if (root / ".gpg-id").is_file() and not yes:
            raise click.ClickException(
                f"{root} is already initialised. Re-running would replace its "
                "recipient, so existing secrets could no longer be decrypted by "
                "the new key. Pass --yes to proceed deliberately."
            )
        _emit(SecretStore(root).init(recipient))

    @secret.command(
        "set", cls=SpecCommand,
        help_spec=CliHelp(
            summary="Store a secret someone else issued, read from stdin.",
            description=(
                "For credentials a PROVIDER issues — a gitea token, a Cloudflare "
                "tunnel token, a GitHub PAT — where `generate` does not apply "
                "because we do not choose the value. The value is read from "
                "stdin or --from-file and NEVER from an option, because an "
                "option value is argv and argv is world-readable via `ps`."
            ),
            examples=(
                Example("pbpaste | {prog} dev secret set gitea/orochi-admin --yes",
                        "Store a token copied from the provider's UI."),
                Example("{prog} dev secret set cf/tunnel --from-file ./new-token --yes",
                        "Store it from a file instead of a pipe."),
            ),
        ),
    )
    @click.argument("name")
    @click.option("--from-file", "from_file", default=None, type=click.Path(),
                  help="Read the value from this file instead of stdin. Not the value itself.")
    @pkg_option
    @dry_run_option
    @yes_option
    def set_cmd(name: str, from_file: str | None, pkg: str, dry_run: bool, yes: bool) -> None:
        if dry_run:
            source = f"the file {from_file}" if from_file else "stdin"
            _dry_run(f"read a value from {source} and store it as {name}")
            return
        if from_file:
            path = Path(from_file).expanduser()
            if not path.is_file():
                raise click.ClickException(f"no such file: {path}")
            value = path.read_text(encoding="utf-8")
        else:
            if sys.stdin.isatty():
                # Refuse rather than prompt: an interactive prompt is what CLI §2
                # forbids, and silently waiting on a TTY looks like a hang.
                raise click.ClickException(
                    "no value on stdin. Pipe it in "
                    "(`printf %s \"$TOKEN\" | … secret set NAME`) or pass "
                    "--from-file PATH. The value must never be a command-line "
                    "argument — `ps` exposes argv to every user on the host."
                )
            value = sys.stdin.read()
        # A trailing newline from a pipe or editor is almost never part of the
        # secret, and a token with a stray \n fails auth in ways that look like
        # a wrong token rather than a formatting bug.
        value = value.rstrip("\n")
        if not value:
            raise click.ClickException(
                "refusing to store an empty value. An empty secret overwrites a "
                "working one and fails later at the point of use, far from here."
            )
        _emit(SecretStore(_root(pkg)).store(name, value, overwrite=yes))

    @secret.command(
        "generate", cls=SpecCommand,
        help_spec=CliHelp(
            summary="Generate a random secret and store it.",
            description="The value is never printed and never enters argv.",
            examples=(
                Example("{prog} dev secret generate mail/sales",
                        "Store a fresh 32-character secret."),
                Example("{prog} dev secret generate db/prod --length 48 --yes",
                        "Replace an existing secret with a longer one."),
            ),
        ),
    )
    @click.argument("name")
    @click.option("--length", default=32, show_default=True, type=int)
    @pkg_option
    @dry_run_option
    @yes_option
    def generate_cmd(name: str, length: int, pkg: str, dry_run: bool, yes: bool) -> None:
        if dry_run:
            _dry_run(f"generate a {length}-character secret and store it as {name}")
            return
        # --yes IS the overwrite consent; there is no separate flag, so the two
        # cannot disagree about whether the caller meant to destroy something.
        _emit(SecretStore(_root(pkg)).generate(name, length=length, overwrite=yes))

    @secret.command(
        "show", cls=SpecCommand,
        help_spec=CliHelp(
            summary="Decrypt a secret to stdout.",
            description=(
                "Requires the private key. The value goes to stdout and every "
                "message to stderr, so command substitution cannot capture an "
                "error as the secret."
            ),
            examples=(
                Example("{prog} dev secret show mail/sales", "Print the secret."),
                Example("MAILPW=$({prog} dev secret show mail/sales)",
                        "Capture it for the moment it is needed."),
            ),
        ),
    )
    @click.argument("name")
    @pkg_option
    @json_option
    def show_cmd(name: str, pkg: str, as_json: bool) -> None:
        _emit(SecretStore(_root(pkg)).show(name), as_json=as_json)

    @secret.command(
        "list", cls=SpecCommand,
        help_spec=CliHelp(
            summary="List stored secret names.",
            examples=(
                Example("{prog} dev secret list", "Names only — never values."),
                Example("{prog} dev secret list --json", "Machine-readable names."),
            ),
        ),
    )
    @pkg_option
    @json_option
    def list_cmd(pkg: str, as_json: bool) -> None:
        _emit(SecretStore(_root(pkg)).list_names(), as_json=as_json)

    @secret.command(
        "create-backup", cls=SpecCommand,
        help_spec=CliHelp(
            summary="Archive the store AND the private key.",
            description=(
                "Losing the store is inconvenient; losing the KEY is terminal, "
                "because every .gpg becomes permanently unreadable. The archive "
                "is passphrase-encrypted and belongs on separate media from the "
                "live key."
            ),
            examples=(
                Example("{prog} dev secret create-backup --dest /media/usb/s.gpg "
                        "--passphrase-file ~/.backup-pp",
                        "Archive store + key to removable media."),
                Example("{prog} dev secret create-backup --dest /media/usb/s.gpg "
                        "--passphrase-file ~/.backup-pp --dry-run",
                        "Show what would be archived."),
            ),
        ),
    )
    @click.option("--dest", required=True, type=click.Path(), help="Where to write the archive.")
    @click.option("--passphrase-file", required=True, type=click.Path(),
                  help="Path to a mode-600 file holding the passphrase. Not the passphrase itself.")
    @click.option("--no-key", is_flag=True, help="Omit the private key (rarely what you want).")
    @pkg_option
    @dry_run_option
    @yes_option
    def create_backup_cmd(dest: str, passphrase_file: str, no_key: bool, pkg: str,
                          dry_run: bool, yes: bool) -> None:
        if dry_run:
            _dry_run(
                f"archive {_root(pkg)} "
                f"({'WITHOUT' if no_key else 'with'} the private key) to {dest}"
            )
            return
        if Path(dest).expanduser().exists() and not yes:
            raise click.ClickException(
                f"{dest} already exists; pass --yes to overwrite it."
            )
        _emit(SecretStore(_root(pkg)).backup(
            Path(dest), _read_passphrase(passphrase_file), secret_key=not no_key))

    @secret.command(
        "restore", cls=SpecCommand,
        help_spec=CliHelp(
            summary="Unpack a backup into a fresh directory.",
            description=(
                "Refuses a non-empty destination, so a restore drill cannot "
                "destroy the live store. The private key is extracted but NOT "
                "imported — import it deliberately once you have confirmed it."
            ),
            examples=(
                Example("{prog} dev secret restore --src /media/usb/s.gpg "
                        "--dest ~/restore-drill --passphrase-file ~/.backup-pp",
                        "Rehearse recovery without touching the live store."),
            ),
        ),
    )
    @click.option("--src", required=True, type=click.Path(), help="The backup archive.")
    @click.option("--dest", required=True, type=click.Path(), help="A FRESH directory.")
    @click.option("--passphrase-file", required=True, type=click.Path(),
                  help="Path to a mode-600 file holding the passphrase. Not the passphrase itself.")
    @pkg_option
    @dry_run_option
    @yes_option
    def restore_cmd(src: str, dest: str, passphrase_file: str, pkg: str,
                    dry_run: bool, yes: bool) -> None:
        if dry_run:
            _dry_run(f"open {src} and unpack it into {dest}")
            return
        _emit(SecretStore(_root(pkg)).restore(
            Path(src), _read_passphrase(passphrase_file), Path(dest)))

    @secret.command(
        "sync", cls=SpecCommand,
        help_spec=CliHelp(
            summary="Commit the store to git and optionally push.",
            description=(
                "Safe over an ordinary remote: the files are already encrypted, "
                "so the remote never sees plaintext."
            ),
            examples=(
                Example("{prog} dev secret sync", "Commit locally."),
                Example("{prog} dev secret sync --remote origin",
                        "Commit and replicate to the other hosts."),
            ),
        ),
    )
    @click.option("--remote", default=None, help="Git remote to push to. Omit to commit only.")
    @pkg_option
    @dry_run_option
    @yes_option
    def sync_cmd(remote: str | None, pkg: str, dry_run: bool, yes: bool) -> None:
        if dry_run:
            target = f" and push to {remote}" if remote else " (no remote; commit only)"
            _dry_run(f"commit {_root(pkg)}{target}")
            return
        _emit(SecretStore(_root(pkg)).sync(remote))

    return secret


__all__ = ["DEFAULT_PKG", "register_secret_group"]


# EOF
