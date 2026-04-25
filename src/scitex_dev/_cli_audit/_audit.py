"""Audit engine — walks a Click command tree and classifies tokens."""

from __future__ import annotations

import gzip
import importlib.metadata as im
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

import click
import yaml

from . import CATALOG, FLAT_KEEPERS


@lru_cache(maxsize=1)
def _load_moby() -> dict[str, set[str]]:
    """Parse vendored Moby POS into {word: {labels}}.

    Labels: noun, verb, verb-t, verb-i.
    """
    db: dict[str, set[str]] = {}
    data = resources.files("scitex_dev._cli_audit").joinpath("data", "mobypos.txt.gz")
    with gzip.open(data.open("rb"), mode="rt", encoding="latin-1") as f:
        for line in f:
            if "\\" not in line:
                continue
            word, pos = line.rstrip("\n").rsplit("\\", 1)
            word = word.lower()
            tags: set[str] = set()
            for c in pos:
                if c == "N":
                    tags.add("noun")
                elif c == "V":
                    tags.add("verb")
                elif c == "t":
                    tags.add("verb-t")
                elif c == "i":
                    tags.add("verb-i")
            if tags:
                db.setdefault(word, set()).update(tags)
    return db


def _load_custom_dict() -> dict[str, set[str]]:
    """Merge project + user custom dictionaries."""
    out: dict[str, set[str]] = {}
    candidates = [
        Path.cwd() / ".scitex" / "dev" / "cli-audit-dict.yaml",
        Path.home() / ".scitex" / "dev" / "cli-audit-dict.yaml",
    ]
    # User is fallback — load it first, project overwrites.
    for path in reversed(candidates):
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        for tag, key in [
            ("noun", "nouns"),
            ("verb-t", "transitive_verbs"),
            ("verb-i", "intransitive_verbs"),
        ]:
            for w in data.get(key, []) or []:
                out.setdefault(w.lower(), set()).add(tag)
    return out


def _classify(token: str) -> set[str]:
    """Return labels for a token using layered lookup."""
    token_lc = token.lower()
    first = token_lc.split("-")[0]

    custom = _load_custom_dict()
    if token_lc in custom:
        return set(custom[token_lc])
    if first in custom:
        return set(custom[first])

    if token_lc in CATALOG:
        return set(CATALOG[token_lc])
    if first in CATALOG:
        return set(CATALOG[first])

    moby = _load_moby()
    if token_lc in moby:
        return set(moby[token_lc])
    if first in moby:
        return set(moby[first])

    return {"unknown"}


@dataclass
class Violation:
    command: str
    rule: str
    message: str


def _walk(cmd: click.BaseCommand, path: list[str], out: list[Violation]) -> None:
    # Skip hidden commands — they are not part of the public CLI surface
    # (typically deprecation redirects kept for back-compat).
    if getattr(cmd, "hidden", False):
        return
    name = cmd.name or "<root>"
    full = " ".join(path + [name]) if path else name
    is_group = isinstance(cmd, click.Group)
    is_root = not path

    if not is_root:
        labels = _classify(name)
        is_leaf = not is_group
        is_compound = "-" in name

        if is_leaf:
            if (
                "noun" in labels
                and not ({"verb-t", "verb-i", "verb", "flat-keeper"} & labels)
                and name not in FLAT_KEEPERS
            ):
                out.append(
                    Violation(
                        full,
                        "§1",
                        f"leaf token looks like a noun — transitive action implied; "
                        f"use '<verb>-{name}' (e.g. start-{name}) or add a sibling verb",
                    )
                )
            if (
                ("verb-t" in labels or "verb" in labels)
                and not is_compound
                and len(path) == 1
                and "noun" not in labels
            ):
                out.append(
                    Violation(
                        full,
                        "§1",
                        f"bare transitive verb at top level — needs an object; "
                        f"use '{name}-<object>' or nest under a noun",
                    )
                )
        else:
            if ({"verb-t", "verb-i", "verb"} & labels) and "noun" not in labels:
                out.append(
                    Violation(
                        full,
                        "§1",
                        "group token looks like a verb — non-leaf subcommands must be nouns",
                    )
                )

        if labels == {"unknown"}:
            out.append(
                Violation(
                    full,
                    "§1c",
                    f"'{name}' not in catalog, custom dict, or Moby POS — "
                    f"add to .scitex/dev/cli-audit-dict.yaml or rename",
                )
            )

    if is_group:
        for sub in cmd.commands.values():
            _walk(sub, (path + [name]) if not is_root else [name], out)


def _resolve_entry_point(package: str) -> click.BaseCommand | None:
    try:
        eps = im.entry_points(group="console_scripts")
    except TypeError:
        eps = im.entry_points().get("console_scripts", [])
    for ep in eps:
        if ep.name == package:
            obj = ep.load()
            if isinstance(obj, click.BaseCommand):
                return obj
            click.echo(
                f"entry point '{package}' is not a click command "
                f"(got {type(obj).__name__})",
                err=True,
            )
            return None
    return None


def run_audit(package: str) -> int:
    cmd = _resolve_entry_point(package)
    if cmd is None:
        click.echo(f"no console script found for '{package}'", err=True)
        return 2

    out: list[Violation] = []
    _walk(cmd, [], out)

    if not out:
        click.echo(f"ok  {package}: no CLI convention violations")
        return 0

    click.echo(f"warn  {package}: {len(out)} warning(s)")
    for v in out:
        click.echo(f"  [{v.rule}] {v.command}: {v.message}")
    return 0
