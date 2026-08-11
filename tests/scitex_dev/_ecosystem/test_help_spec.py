#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for spec-built help (CliHelp / SpecCommand / SpecGroup).

Doctrine under test:
``scitex_dev/_skills/general/03_interface/02_cli/10_help-format.md``
("Spec-built help" section) — help is data validated at import time
(summary one line <=78 chars, leaves need >=1 example, ``{prog}``
placeholder keeps examples brand-neutral) and rendered in a fixed
section order with ``{prog}`` resolved from the actual invocation path.

No mocks: rendering is exercised through real Click commands via
``CliRunner``; version resolution goes through the real
``importlib.metadata`` against scitex-dev's own installed dist.
"""

from __future__ import annotations

import functools
from importlib.metadata import PackageNotFoundError, version

import click
import pytest
from click.testing import CliRunner

from scitex_dev._ecosystem.help_spec import (
    CliHelp,
    Example,
    SpecCommand,
    SpecGroup,
    render_epilog,
    render_help,
)


def _leaf_help_spec(**overrides) -> CliHelp:
    """A valid leaf spec; keyword overrides mutate individual fields."""
    fields = dict(
        summary="Run one demo action.",
        examples=(Example("{prog} run --fast", "Run quickly."),),
    )
    fields.update(overrides)
    return CliHelp(**fields)


def _build_spec_cli():
    """A SpecGroup with one categorized SpecCommand leaf."""

    @click.group(
        cls=SpecGroup,
        help_spec=CliHelp(summary="Demo group for spec-built help."),
        command_categories=[("Core", ["run"])],
    )
    def cli():
        pass

    @cli.command("run", cls=SpecCommand, help_spec=_leaf_help_spec())
    def run_cmd():
        click.echo("ran")

    return cli


# ── validation (fails at import time, not runtime) ──────────────────────────


def test_summary_over_78_chars_rejected():
    # Arrange
    long_summary = "x" * 79
    # Act
    construct_spec = functools.partial(CliHelp, summary=long_summary)
    # Assert
    with pytest.raises(ValueError):
        construct_spec()


def test_summary_with_78_chars_accepted():
    # Arrange
    boundary_summary = "x" * 78
    # Act
    spec = CliHelp(summary=boundary_summary)
    # Assert
    assert spec.summary == boundary_summary


def test_multi_line_summary_rejected():
    # Arrange
    two_line_summary = "First line.\nSecond line."
    # Act
    construct_spec = functools.partial(CliHelp, summary=two_line_summary)
    # Assert
    with pytest.raises(ValueError):
        construct_spec()


def test_empty_summary_rejected_loudly():
    # Arrange
    blank_summary = "   "
    # Act
    construct_spec = functools.partial(CliHelp, summary=blank_summary)
    # Assert
    with pytest.raises(ValueError):
        construct_spec()


def test_example_without_prog_placeholder_rejected():
    # Arrange
    hardwired_cmd = "run --fast"
    # Act
    construct_example = functools.partial(Example, hardwired_cmd)
    # Assert
    with pytest.raises(ValueError):
        construct_example()


def test_example_with_brand_prefix_rejected():
    # Arrange — contains {prog} yet still leads with a hardcoded brand
    branded_cmd = "scitex-plt render {prog}"
    # Act
    construct_example = functools.partial(Example, branded_cmd)
    # Assert
    with pytest.raises(ValueError):
        construct_example()


def test_leaf_without_examples_rejected():
    # Arrange
    example_free_spec = CliHelp(summary="No examples here.")
    # Act
    construct_leaf = functools.partial(
        SpecCommand, "run", callback=lambda: None, help_spec=example_free_spec
    )
    # Assert
    with pytest.raises(ValueError):
        construct_leaf()


def test_group_without_examples_accepted():
    # Arrange — the >=1-example rule binds leaves only, not groups
    example_free_spec = CliHelp(summary="Group needs no example.")
    # Act
    group = SpecGroup("grp", help_spec=example_free_spec)
    # Assert
    assert group._help_spec is example_free_spec


def test_non_clihelp_spec_rejected():
    # Arrange
    plain_string_spec = "just a help string"
    # Act
    construct_leaf = functools.partial(
        SpecCommand, "run", callback=lambda: None, help_spec=plain_string_spec
    )
    # Assert
    with pytest.raises(TypeError):
        construct_leaf()


# ── renderers ────────────────────────────────────────────────────────────────


def test_render_help_joins_description_paragraphs():
    # Arrange
    spec = CliHelp(summary="Summary line.", description=("Para one.", "Para two."))
    # Act
    body = render_help(spec)
    # Assert
    assert body == "Summary line.\n\nPara one.\n\nPara two."


def test_version_of_renders_dist_version_inline():
    # Arrange — scitex-dev's own dist, resolved through real metadata
    spec = CliHelp(summary="Demo summary.", version_of="scitex-dev")
    # Act
    first_line = render_help(spec).splitlines()[0]
    # Assert
    assert first_line == f"scitex-dev (v{version('scitex-dev')}) — Demo summary."


def test_missing_dist_states_the_non_answer_instead_of_raising():
    # Arrange — REPLACES test_missing_dist_raises_package_not_found, and the
    # replacement is deliberate rather than a test bent to fit new code.
    #
    # The old rule ("no silent fallback: unknown dist must fail loudly") was
    # protecting the right thing — never invent a plausible version — but it
    # spelled "unresolvable" as "crash". `SpecGroup.__init__` renders help
    # while the `@click.group` decorator is being evaluated, so the raise
    # landed at IMPORT time: every package adopting help_spec was dead under
    # `python -m pkg` from a source checkout, which is a normal invocation
    # on a host that has the repo and not the wheel.
    #
    # Reported by scitex-storage and sac 2026-08-11, hit while scheduling
    # the free-space alarm the compute-04 incident needed.
    #
    # What is preserved: no fabricated number (pinned by the next test).
    spec = CliHelp(summary="Demo summary.", version_of="scitex-no-such-dist")
    # Act
    first_line = render_help(spec).splitlines()[0]
    # Assert
    assert first_line == (
        "scitex-no-such-dist (version unresolved: no installed "
        "distribution) — Demo summary."
    )


def test_missing_dist_never_renders_a_plausible_version():
    # Arrange — the half of the old rule that still holds, kept as its own
    # assertion so a future edit cannot satisfy the test above with "v0.0.0".
    spec = CliHelp(summary="Demo summary.", version_of="scitex-no-such-dist")
    # Act
    text = render_help(spec)
    # Assert
    assert "v0." not in text


def test_epilog_sections_render_in_fixed_order():
    # Arrange
    spec = _leaf_help_spec(
        exit_codes={0: "success", 2: "usage error"},
        config_resolution=("a.yaml → $DEMO_CONFIG → defaults",),
        see_also=("{prog} docs",),
    )
    headers = ["Examples:", "Exit codes:", "Config resolution:", "See also:"]
    # Act
    epilog = render_epilog(spec, "demo")
    # Assert
    assert [epilog.index(h) for h in headers] == sorted(
        epilog.index(h) for h in headers
    )


def test_epilog_substitutes_prog_placeholder():
    # Arrange
    spec = _leaf_help_spec()
    # Act
    epilog = render_epilog(spec, "demo")
    # Assert
    assert "$ demo run --fast" in epilog


def test_example_notes_share_one_column():
    # Arrange — commands of different length must not stagger the notes
    spec = _leaf_help_spec(
        examples=(
            Example("{prog} go", "First note."),
            Example("{prog} go --very-long-flag", "Second note."),
        )
    )
    # Act
    lines = [
        line
        for line in render_epilog(spec, "demo").splitlines()
        if line.startswith("  $")
    ]
    # Assert
    assert lines[0].index("First note.") == lines[1].index("Second note.")


def test_exit_codes_render_code_meaning_rows():
    # Arrange
    spec = _leaf_help_spec(exit_codes={0: "success", 2: "usage error"})
    # Act
    epilog = render_epilog(spec, "demo")
    # Assert
    assert "  0  success" in epilog


# ── SpecCommand / SpecGroup rendering through Click ──────────────────────────


def test_help_spec_attribute_stored_for_auditor():
    # Arrange
    cli = _build_spec_cli()
    # Act
    leaf = cli.commands["run"]
    # Assert
    assert isinstance(leaf._help_spec, CliHelp)


def test_leaf_help_resolves_actual_invocation_path():
    # Arrange — {prog} must follow the mount (umbrella vs standalone)
    cli = _build_spec_cli()
    # Act
    result = CliRunner().invoke(
        cli, ["run", "--help"], prog_name="scitex demo"
    )
    # Assert
    assert "$ scitex demo run --fast" in result.output


def test_group_help_renders_category_section():
    # Arrange — SpecGroup inherits CategorizedGroup section rendering
    cli = _build_spec_cli()
    # Act
    result = CliRunner().invoke(cli, ["--help"], prog_name="demo")
    # Assert
    assert "Core:" in result.output


def test_group_summary_precedes_usage_line():
    # Arrange — doctrine §4 order: summary/description before usage
    cli = _build_spec_cli()
    # Act
    output = CliRunner().invoke(cli, ["--help"], prog_name="demo").output
    # Assert
    assert output.index("Demo group for spec-built help.") < output.index("Usage:")


def test_spec_command_exported_from_ecosystem_facade():
    # Arrange
    from scitex_dev import ecosystem
    # Act
    exported = ecosystem.SpecCommand
    # Assert
    assert exported is SpecCommand
