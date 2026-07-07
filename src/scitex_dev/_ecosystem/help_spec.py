"""Structured help specs — help text as validated data (doctrine §4).

Implements the "Spec-built help" contract in
``scitex_dev/_skills/general/03_interface/02_cli/10_help-format.md``
(slice 3 of the CLI-standardization plan): free-form help strings drift,
so help is declared as a :class:`CliHelp` dataclass, validated at import
time, and rendered uniformly by :class:`SpecCommand` /
:class:`SpecGroup`.

Rendered section order is FIXED ecosystem-wide: summary line (with the
version via ``version_of`` + ``importlib.metadata.version``),
description, usage, options (+ categorized commands on groups),
examples, exit codes, config resolution, see-also.

Validation (fails at import, not at runtime):

* ``summary`` is ONE line and <=78 characters.
* Example commands use the ``{prog}`` placeholder, never a hardcoded
  brand prefix (``scitex-plt ...`` X, ``{prog} ...`` OK) — the renderer
  substitutes ``ctx.find_root().info_name`` so the same spec shows the
  right invocation standalone (``scitex-plt``) and under the umbrella
  (``scitex plt``).
* Leaf commands (:class:`SpecCommand`) declare at least one example.
* ``version_of`` resolves through ``importlib.metadata`` at render
  time; a missing distribution raises loudly (no silent fallback).

Every spec-built command carries ``cmd._help_spec`` so the CLI auditor
(slice 4, rule 4b) can verify spec-built help statically.

Usage::

    import click
    from scitex_dev.ecosystem import CliHelp, Example, SpecCommand, SpecGroup

    @click.group(
        cls=SpecGroup,
        command_categories=[("Core", ["run"])],
        help_spec=CliHelp(
            summary="Frobnicate scientific things.",
            version_of="scitex-frob",
        ),
    )
    def main():
        pass

    @main.command(
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Run one frobnication.",
            examples=(Example("{prog} run spec.yaml", "Run from a spec."),),
        ),
    )
    def run():
        pass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import version as _dist_version
from typing import Mapping, Sequence

import click

from .click_helpers import CategorizedGroup

__all__ = [
    "CliHelp",
    "Example",
    "SpecCommand",
    "SpecGroup",
    "render_epilog",
    "render_help",
]

_SUMMARY_MAX_CHARS = 78
_BANNED_CMD_PREFIXES = ("scitex ", "scitex-")


@dataclass(frozen=True)
class Example:
    """One concrete invocation example: a command line plus a short note."""

    cmd: str
    note: str = ""

    def __post_init__(self) -> None:
        if "{prog}" not in self.cmd:
            raise ValueError(
                f"Example.cmd must use the {{prog}} placeholder "
                f"(got {self.cmd!r}) — the renderer substitutes the actual "
                f"invocation path so specs stay brand-neutral"
            )
        head = self.cmd.lstrip()
        if head.startswith(_BANNED_CMD_PREFIXES):
            raise ValueError(
                f"Example.cmd must not start with a hardcoded brand prefix "
                f"(got {self.cmd!r}) — write '{{prog}} ...' so the same spec "
                f"renders correctly standalone and under the umbrella"
            )


def _as_paragraph_tuple(value: str | Sequence[str]) -> tuple[str, ...]:
    """Normalize a description/config block to a tuple of paragraphs."""
    if isinstance(value, str):
        return tuple(p.strip("\n") for p in value.split("\n\n") if p.strip())
    return tuple(value)


@dataclass(frozen=True)
class CliHelp:
    """Validated help spec — the enforced construction method for help.

    ``description`` holds blank-line-separated paragraphs (a plain
    string is split on blank lines). ``exit_codes`` accepts a mapping or
    ``(code, meaning)`` pairs. ``version_of`` names the distribution
    whose version renders inline in the summary line.
    """

    summary: str
    description: tuple[str, ...] = field(default=())
    examples: tuple[Example, ...] = field(default=())
    exit_codes: tuple[tuple[int, str], ...] = field(default=())
    config_resolution: tuple[str, ...] = field(default=())
    see_also: tuple[str, ...] = field(default=())
    version_of: str | None = None

    def __post_init__(self) -> None:
        # Normalize sequence inputs to immutable tuples (frozen dataclass).
        object.__setattr__(
            self, "description", _as_paragraph_tuple(self.description)
        )
        object.__setattr__(self, "examples", tuple(self.examples))
        exit_pairs = (
            self.exit_codes.items()
            if isinstance(self.exit_codes, Mapping)
            else self.exit_codes
        )
        object.__setattr__(
            self,
            "exit_codes",
            tuple((int(code), str(meaning)) for code, meaning in exit_pairs),
        )
        object.__setattr__(
            self, "config_resolution", _as_paragraph_tuple(self.config_resolution)
        )
        object.__setattr__(self, "see_also", tuple(self.see_also))

        if not self.summary or not self.summary.strip():
            raise ValueError("CliHelp.summary must be a non-empty line")
        if "\n" in self.summary:
            raise ValueError(
                "CliHelp.summary must be ONE line — move extra prose into "
                "description paragraphs"
            )
        if len(self.summary) > _SUMMARY_MAX_CHARS:
            raise ValueError(
                f"CliHelp.summary must be <={_SUMMARY_MAX_CHARS} chars "
                f"(got {len(self.summary)}): {self.summary!r}"
            )
        for example in self.examples:
            if not isinstance(example, Example):
                raise TypeError(
                    f"CliHelp.examples entries must be Example instances "
                    f"(got {type(example).__name__}: {example!r})"
                )


def render_help(spec: CliHelp) -> str:
    """Render the help body: summary line + description paragraphs.

    With ``version_of`` set, the summary line is the doctrine-canonical
    ``<dist> (vX.Y.Z) — <summary>`` — the version resolved via
    ``importlib.metadata`` at render time. A missing distribution raises
    ``importlib.metadata.PackageNotFoundError`` loudly: pyproject.toml
    is the single source of truth, never a hardcoded fallback string.
    """
    if spec.version_of:
        first_line = (
            f"{spec.version_of} (v{_dist_version(spec.version_of)}) — "
            f"{spec.summary}"
        )
    else:
        first_line = spec.summary
    return "\n\n".join((first_line, *spec.description))


def render_epilog(spec: CliHelp, prog: str) -> str:
    """Render the fixed-order epilog sections with ``{prog}`` substituted.

    Section order is canonical: Examples / Exit codes / Config
    resolution / See also. Example notes are aligned to a shared column
    past the longest command so they read as a two-column table.
    """
    sections: list[str] = []

    if spec.examples:
        cmds = [ex.cmd.replace("{prog}", prog) for ex in spec.examples]
        note_column = max(len(cmd) for cmd in cmds)
        lines = ["Examples:"]
        for cmd, example in zip(cmds, spec.examples):
            if example.note:
                lines.append(f"  $ {cmd:<{note_column}}  {example.note}")
            else:
                lines.append(f"  $ {cmd}")
        sections.append("\n".join(lines))

    if spec.exit_codes:
        code_column = max(len(str(code)) for code, _ in spec.exit_codes)
        lines = ["Exit codes:"]
        for code, meaning in spec.exit_codes:
            lines.append(f"  {code:>{code_column}}  {meaning}")
        sections.append("\n".join(lines))

    if spec.config_resolution:
        lines = ["Config resolution:"]
        lines.extend(f"  {row}" for row in spec.config_resolution)
        sections.append("\n".join(lines))

    if spec.see_also:
        lines = ["See also:"]
        lines.extend(f"  {ref.replace('{prog}', prog)}" for ref in spec.see_also)
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


class _SpecRendered:
    """Shared spec plumbing for :class:`SpecCommand` / :class:`SpecGroup`.

    Sets ``help`` / ``epilog`` from the renderers, stores
    ``self._help_spec`` for the static auditor, and re-renders at
    ``--help`` time so ``{prog}`` is the ACTUAL invocation path
    (``ctx.find_root().info_name`` — correct under both ``scitex-dev``
    and umbrella ``scitex dev`` passthrough mounts).
    """

    def __init__(self, *args, help_spec: CliHelp, **kwargs):
        if not isinstance(help_spec, CliHelp):
            raise TypeError(
                f"help_spec must be a CliHelp instance "
                f"(got {type(help_spec).__name__}) — spec-built help is the "
                f"enforced construction method (doctrine §4)"
            )
        kwargs["help"] = render_help(help_spec)
        kwargs.setdefault("short_help", help_spec.summary)
        # Static placeholder epilog; format_epilog re-renders with the
        # resolved prog at --help time.
        kwargs["epilog"] = render_epilog(help_spec, prog="{prog}")
        super().__init__(*args, **kwargs)
        self._help_spec = help_spec

    def format_help(self, ctx, formatter) -> None:
        """Doctrine §4 order: summary/description, usage, options, epilog."""
        self.format_help_text(ctx, formatter)
        formatter.write_paragraph()
        self.format_usage(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_epilog(ctx, formatter)

    def format_help_text(self, ctx, formatter) -> None:
        """Write the body unindented; re-render so version_of is live."""
        for index, paragraph in enumerate(render_help(self._help_spec).split("\n\n")):
            if index:
                formatter.write_paragraph()
            formatter.write_text(paragraph)

    def format_epilog(self, ctx, formatter) -> None:
        """Write the epilog verbatim with ``{prog}`` resolved from ctx."""
        prog = ctx.find_root().info_name or ""
        epilog = render_epilog(self._help_spec, prog)
        if not epilog:
            return
        formatter.write_paragraph()
        formatter.write(epilog + "\n")


class SpecCommand(_SpecRendered, click.Command):
    """Leaf command whose help is built from a :class:`CliHelp` spec.

    Leaves must document at least one concrete example (doctrine §4
    item 3) — enforced here, not on groups.
    """

    def __init__(self, *args, help_spec: CliHelp, **kwargs):
        if isinstance(help_spec, CliHelp) and not help_spec.examples:
            raise ValueError(
                f"SpecCommand requires at least one Example in help_spec "
                f"(summary: {help_spec.summary!r}) — every leaf documents a "
                f"concrete invocation (doctrine §4)"
            )
        super().__init__(*args, help_spec=help_spec, **kwargs)


class SpecGroup(_SpecRendered, CategorizedGroup):
    """Group whose help is built from a :class:`CliHelp` spec.

    Inherits :class:`CategorizedGroup` so the command list renders under
    the fixed §4a category headers. Categories come from the
    ``COMMAND_CATEGORIES`` class attribute or the ``command_categories``
    keyword (the §4a doctrine-example shape).
    """

    def __init__(
        self,
        *args,
        help_spec: CliHelp,
        command_categories: Sequence[tuple[str, Sequence[str]]] | None = None,
        **kwargs,
    ):
        super().__init__(*args, help_spec=help_spec, **kwargs)
        if command_categories is not None:
            self.COMMAND_CATEGORIES = tuple(
                (section, tuple(names)) for section, names in command_categories
            )
