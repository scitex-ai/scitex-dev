#!/usr/bin/env python3
"""`audit_all_for_package(path=None)` must NAME the tree it is guessing from.

`path=None` is documented as "a compatibility shim, not a recommendation"
— and it is also the default every caller gets, so the documented-wrong
shape was the SILENT one. Guessing is survivable; guessing without
saying from where is what turns a wrong-tree audit into a green that
nobody double-checks (scitex-storage's third suggestion, 2026-07-29).

The warning goes to a stream rather than through `warnings.warn` on
purpose: packages running pytest with `-W error` would otherwise see a
working gate hard-fail on a diagnostic.

No mocks (PA-306 / STX-NM002): the emit target is a real injected
stream, not a patched module attribute.
"""

from __future__ import annotations

import io
from pathlib import Path

from scitex_dev.testing._audit_conformance import (
    guessed_path_warning,
    warn_on_guessed_path,
)


class TestGuessedPathWarningNamesTheCwd:
    """The message must contain the actual directory, not a generic scold."""

    def test_message_contains_the_given_cwd(self, tmp_path):
        """A caller can compare the named path against what they meant."""
        # Arrange
        here = tmp_path / "some" / "checkout"
        here.mkdir(parents=True)
        # Act
        message = guessed_path_warning(cwd=here)
        # Assert
        assert str(here) in message

    def test_message_defaults_to_the_process_cwd(self):
        """No argument: the real cwd is what audit-all would guess from."""
        # Arrange
        expected = str(Path.cwd())
        # Act
        message = guessed_path_warning()
        # Assert
        assert expected in message

    def test_message_names_the_parameter_that_fixes_it(self, tmp_path):
        """A warning that does not say what to do is noise."""
        # Arrange
        expected = "path=Path(__file__).resolve().parents[N]"
        # Act
        message = guessed_path_warning(cwd=tmp_path)
        # Assert
        assert expected in message

    def test_message_is_labelled_a_warning(self, tmp_path):
        """CI logs are grepped by level prefix."""
        # Arrange
        expected_prefix = "warning: "
        # Act
        message = guessed_path_warning(cwd=tmp_path)
        # Assert
        assert message.startswith(expected_prefix)


class TestWarnOnGuessedPathEmits:
    """The warning must actually reach a stream, not just be constructible."""

    def test_warning_is_written_to_the_given_stream(self, tmp_path):
        """Real stream seam — no monkeypatching of sys.stderr."""
        # Arrange
        stream = io.StringIO()
        # Act
        warn_on_guessed_path(cwd=tmp_path, stream=stream)
        # Assert
        assert str(tmp_path) in stream.getvalue()

    def test_returned_text_matches_what_was_written(self, tmp_path):
        """The return value is usable by callers that want to re-report it."""
        # Arrange
        stream = io.StringIO()
        # Act
        returned = warn_on_guessed_path(cwd=tmp_path, stream=stream)
        # Assert
        assert stream.getvalue().rstrip("\n") == returned
