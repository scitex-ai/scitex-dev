#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev dev`` — the canonical §13 self-maintenance group.

§13 (operator directive) mandates that every self-maintenance surface a package
ships mounts under ONE group named ``dev``, and that package plumbing is never
mounted at top level. The spec is explicit that it enforces the *nesting*, not a
frozen verb list:

    "Each of the six verbs is itself the sub-surface (a group or a leaf as the
     package needs); §13 enforces the nesting, not any fixed verb set inside
     each one."

This module creates that group. It is step 1 of
``scitex-dev-unified-dev-command-group-architecture-20260718`` — the audit rule
(``_cli/audit/_summary/_dev_group.py``) already ships and currently fires
against scitex-dev itself, which is why counting adoption reads as "no rule".

``secret`` is the first verb mounted here. It lands at ``<pkg> dev secret`` from
the outset rather than at a top-level ``secret`` that would later need
migrating: a workaround baked into a published command path outlives the reason
for it.
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup
from ...secret import OK, SecretStore

_DEFAULT_PKG = "dev"


def _store_root(pkg: str) -> Path:
    """Resolve the store root for ``pkg``.

    Follows the fleet's runtime-state convention (``~/.scitex/<pkg>/…``) and is
    overridable for tests and for a tenant-scoped root, because the recipient —
    not the path — is what enforces isolation.
    """
    override = os.environ.get("SCITEX_DEV_SECRET_ROOT")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".scitex" / pkg / "secret"


def _emit(result) -> None:
    """Print a result and exit non-zero on failure.

    The DETAIL always goes to stderr and the VALUE always to stdout, so a
    consumer doing ``KEY=$(… secret show name)`` can never capture an error
    message as the secret. That is the decrypt.sh defect — a 61-byte ANSI error
    string ingested as a password — closed at the CLI boundary too, not only
    inside the library.
    """
    if result.code == OK and result.value is not None:
        click.echo(result.value, nl=False)
        click.echo(result.detail, err=True)
        return
    click.echo(result.detail, err=True)
    if result.names:
        for name in result.names:
            click.echo(name)
    if result.code != OK:
        raise SystemExit(1)


def register_dev_commands(main_group) -> click.Group:
    """Register ``scitex-dev dev`` and its verbs on ``main_group``."""

    @main_group.group(
        "dev",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Package self-maintenance surfaces (§13 canonical group).",
            description=(
                "One group for every self-maintenance surface this package "
                "ships. §13 enforces the nesting rather than a fixed verb set, "
                "so verbs are added here as each surface migrates off the top "
                "level."
            ),
            examples=(
                Example("{prog} dev secret list", "List stored secret names."),
            ),
        ),
    )
    @click.pass_context
    def dev(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    _register_secret(dev)
    return dev


def _register_secret(dev: click.Group) -> None:
    @dev.group(
        "secret",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="GPG-backed credential store (pass-compatible layout).",
            description=(
                "Stores one gpg-encrypted file per secret under "
                "~/.scitex/<pkg>/secret, in the layout `pass` reads, so either "
                "tool operates on the same store. Values never appear in "
                "argv. Decryption requires the private key, so `show` only "
                "works where that key lives."
            ),
            examples=(
                Example("{prog} dev secret init --recipient you@example.com",
                        "Create the store."),
                Example("{prog} dev secret generate mail/sales",
                        "Generate and store a random secret."),
                Example("{prog} dev secret show mail/sales",
                        "Print the secret to stdout."),
                Example("{prog} dev secret backup --dest ~/backup.gpg",
                        "Archive the store AND the private key."),
            ),
        ),
    )
    @click.pass_context
    def secret(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    pkg_option = click.option(
        "--pkg", default=_DEFAULT_PKG, show_default=True,
        help="Which package's store to operate on (~/.scitex/<pkg>/secret).",
    )

    @secret.command(
        "init", cls=SpecCommand,
        help_spec=CliHelp(
            summary="Create the store for a recipient.",
            examples=(
                Example("{prog} dev secret init --recipient you@example.com",
                        "Create ~/.scitex/dev/secret encrypted to that key."),
            ),
        ),
    )
    @click.option("--recipient", required=True,
                  help="GPG key id or uid that will be able to decrypt.")
    @pkg_option
    def init_cmd(recipient: str, pkg: str) -> None:
        _emit(SecretStore(_store_root(pkg)).init(recipient))

    @secret.command(
        "generate", cls=SpecCommand,
        help_spec=CliHelp(
            summary="Generate a random secret and store it.",
            description="The value is never printed and never enters argv.",
            examples=(
                Example("{prog} dev secret generate mail/sales",
                        "Store a fresh 32-character secret."),
                Example("{prog} dev secret generate db/prod --length 48 --overwrite",
                        "Replace an existing secret with a longer one."),
            ),
        ),
    )
    @click.argument("name")
    @click.option("--length", default=32, show_default=True, type=int)
    @click.option("--overwrite", is_flag=True, help="Replace an existing secret.")
    @pkg_option
    def generate_cmd(name: str, length: int, overwrite: bool, pkg: str) -> None:
        _emit(SecretStore(_store_root(pkg)).generate(name, length=length, overwrite=overwrite))

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
    def show_cmd(name: str, pkg: str) -> None:
        _emit(SecretStore(_store_root(pkg)).show(name))

    @secret.command(
        "list", cls=SpecCommand,
        help_spec=CliHelp(
            summary="List stored secret names.",
            examples=(
                Example("{prog} dev secret list", "Names only — never values."),
            ),
        ),
    )
    @pkg_option
    def list_cmd(pkg: str) -> None:
        _emit(SecretStore(_store_root(pkg)).list_names())

    @secret.command(
        "backup", cls=SpecCommand,
        help_spec=CliHelp(
            summary="Archive the store AND the private key.",
            description=(
                "Losing the store is inconvenient; losing the KEY is terminal, "
                "because every .gpg becomes permanently unreadable. The archive "
                "is passphrase-encrypted and belongs on separate media from the "
                "live key."
            ),
            examples=(
                Example("{prog} dev secret backup --dest /media/usb/scitex-secrets.gpg",
                        "Archive store + key to removable media."),
            ),
        ),
    )
    @click.option("--dest", required=True, type=click.Path(), help="Where to write the archive.")
    @click.option("--no-key", is_flag=True, help="Omit the private key (rarely what you want).")
    @pkg_option
    def backup_cmd(dest: str, no_key: bool, pkg: str) -> None:
        passphrase = click.prompt("Backup passphrase", hide_input=True, confirmation_prompt=True)
        _emit(SecretStore(_store_root(pkg)).backup(Path(dest), passphrase, secret_key=not no_key))

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
                Example("{prog} dev secret restore --src /media/usb/scitex-secrets.gpg "
                        "--dest ~/restore-drill",
                        "Rehearse recovery without touching the live store."),
            ),
        ),
    )
    @click.option("--src", required=True, type=click.Path(), help="The backup archive.")
    @click.option("--dest", required=True, type=click.Path(), help="A FRESH directory.")
    @pkg_option
    def restore_cmd(src: str, dest: str, pkg: str) -> None:
        passphrase = click.prompt("Backup passphrase", hide_input=True)
        _emit(SecretStore(_store_root(pkg)).restore(Path(src), passphrase, Path(dest)))

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
    def sync_cmd(remote: str | None, pkg: str) -> None:
        _emit(SecretStore(_store_root(pkg)).sync(remote))
