"""Facade attribution reads real published Click classes without execution."""

import sys

import click

from scitex_dev._cli.audit._summary._facade_source import published_facade_module
from scitex_dev.ecosystem import CliHelp, SpecGroup


def test_published_shared_group_class_has_its_loaded_source():
    # Arrange
    command = SpecGroup("inspect", help_spec=CliHelp(summary="Inspect metadata."))

    # Act
    binding = published_facade_module(command)

    # Assert
    assert binding == (SpecGroup.__module__, sys.modules[SpecGroup.__module__])


def test_plain_click_group_reports_click_source_not_an_application_owner():
    # Arrange
    command = click.Group("inspect")

    # Act
    binding = published_facade_module(command)

    # Assert
    assert binding == (click.Group.__module__, sys.modules[click.Group.__module__])


def test_non_command_object_has_no_facade_binding():
    # Arrange
    value = object()

    # Act
    binding = published_facade_module(value)

    # Assert
    assert binding is None
