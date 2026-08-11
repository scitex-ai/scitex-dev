# -*- coding: utf-8 -*-
"""A source checkout must not be killed by a version string in a help header.

`SpecGroup.__init__` renders help while the `@click.group` DECORATOR is
still being evaluated. So when `render_help` raised `PackageNotFoundError`
for a distribution with no metadata, the CLI did not degrade — it failed to
IMPORT. `python -m <pkg> <anything>` was dead for every package adopting
this module and ever invoked from a tree rather than an install.

Reported by scitex-storage and sac 2026-08-11, found while trying to
schedule the free-space alarm the 2026-08-09 compute-04 incident needed
(364 MB free, nothing reported it). Blocked two days by a help header.

The original rule stands and is tested here: NO fabricated version. What
changed is that "unresolvable" stopped being spelled as "crash" — the
version has three states, and the middle one now says so.

No mocks (NM001-003): the tests use a distribution name that genuinely has
no metadata, which is precisely the real condition.
One assert per test (STX-TQ007), AAA markers (STX-TQ002).
"""

from __future__ import annotations

import click

from scitex_dev._ecosystem.help_spec import (
    CliHelp,
    SpecGroup,
    render_help,
)

#: A name no installed distribution can claim — the checkout condition.
_ABSENT = "scitex-not-a-real-distribution-xyz"


def test_render_help_does_not_raise_for_an_uninstalled_distribution():
    # Arrange — the exact shape a source checkout produces.
    spec = CliHelp(summary="Do a thing.", version_of=_ABSENT)
    # Act
    text = render_help(spec)
    # Assert
    assert text


def test_the_unresolved_version_is_stated_not_fabricated():
    # Arrange — the original rule: pyproject is the source of truth, never a
    # hardcoded fallback. A plausible "0.0.0" here would be worse than the
    # crash, because it would be believed.
    spec = CliHelp(summary="Do a thing.", version_of=_ABSENT)
    # Act
    text = render_help(spec)
    # Assert
    assert "version unresolved" in text


def test_no_fake_version_number_appears():
    # Arrange — POSITIVE CONTROL for the test above: "version unresolved"
    # being present does not prove a number is absent, and the number is the
    # thing that would mislead.
    spec = CliHelp(summary="Do a thing.", version_of=_ABSENT)
    # Act
    text = render_help(spec)
    # Assert
    assert "v0.0.0" not in text


def test_a_group_can_be_CONSTRUCTED_against_an_uninstalled_dist():
    # Arrange — the actual failure: this ran at decorator-evaluation time,
    # so the import died before any of the consuming package's code ran.
    spec = CliHelp(summary="Do a thing.", version_of=_ABSENT)

    # Act
    @click.group(cls=SpecGroup, help_spec=spec)
    def cli():  # pragma: no cover - never invoked, construction is the test
        pass

    # Assert
    assert cli.help


def test_an_INSTALLED_dist_still_renders_its_real_version():
    # Arrange — SECOND POSITIVE CONTROL. Every test above passes if version
    # resolution were removed entirely, which would silently drop the
    # version from every help header in the ecosystem.
    spec = CliHelp(summary="Do a thing.", version_of="scitex-dev")
    # Act
    text = render_help(spec)
    # Assert
    assert "version unresolved" not in text


# EOF
