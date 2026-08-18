#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The failure message names WHICH auditor measured the tree.

THE QUESTION IT ANSWERS, in sac's words (2026-08-18): "DID THE CODE
CHANGE OR DID THE RULER CHANGE?" It is the first question any reader of
a red gate has, it decides whether they go looking at their own diff or
at PyPI, and the output could not answer it.

sac's develop went red with no commit behind it. They declare
`scitex-dev>=0.49.2` — a FLOOR — CI resolves the newest at job time, and
five minor releases of the rule corpus had landed in between. Several
codes in the failure were ones the older auditor cannot emit at all.

Three independent requests for this one line: scitex-app ("the useful
payload was not 'you are red' — it was the AUDITOR VERSION PAIR"),
scitex-ui, and sac.
"""

from __future__ import annotations

from scitex_dev.testing._auditor_identity import auditor_identity
from scitex_dev.testing._audit_outcome import unknown_message, violations_message

_A_FINDING = "ERRO:   [E] [PS-140 §2 gate-skip-scope] a.py"


class TestTheIdentityIsMeasuredNotAssumed:
    def test_a_real_binary_reports_a_version(self):
        # Arrange
        import shutil

        binary = shutil.which("scitex-dev") or "scitex-dev"
        # Act
        identity = auditor_identity(binary)
        # Assert
        assert "scitex-dev" in identity

    def test_the_identity_names_the_path_it_asked(self):
        """Two scitex-devs can be installed; the version alone is ambiguous.

        `audit-all` resolves sub-auditors from PATH, so the binary that
        graded the tree is not necessarily the one this interpreter
        would import. Naming the path is what makes the version
        checkable rather than merely stated.
        """
        # Arrange
        import shutil

        binary = shutil.which("scitex-dev") or "scitex-dev"
        # Act
        identity = auditor_identity(binary)
        # Assert
        assert binary in identity

    def test_an_absent_binary_says_UNKNOWN_rather_than_inventing_one(self):
        """A fabricated version would be indistinguishable from a measured one.

        This line exists to be trusted, so its failure mode must be
        loud. A default here would be a well-formed lie.
        """
        # Arrange
        missing = "/nonexistent/scitex-dev"
        # Act
        identity = auditor_identity(missing)
        # Assert
        assert identity.startswith("UNKNOWN")

    def test_the_unknown_form_still_names_what_it_tried(self):
        # Arrange
        missing = "/nonexistent/scitex-dev"
        # Act
        identity = auditor_identity(missing)
        # Assert
        assert missing in identity


class TestBothFailureMessagesCarryIt:
    def test_the_violation_report_names_the_auditor(self):
        # Arrange
        ident = "scitex-dev 0.53.0 (/opt/venv/bin/scitex-dev)"
        # Act
        message = violations_message("sac", "cmd", 1, [_A_FINDING], "", audited_by=ident)
        # Assert
        assert f"audited by {ident}" in message

    def test_the_could_not_run_report_names_it_too(self):
        """A stale auditor answering "not-auditable" is sac's exact case.

        The COULD-NOT-RUN path is where an OLD auditor is most likely to
        land, so omitting the version there would miss the reading it
        was built for.
        """
        # Arrange
        ident = "scitex-dev 0.48.0 (/usr/bin/scitex-dev)"
        # Act
        message = unknown_message("sac", "cmd", 2, ["could not run"], "", audited_by=ident)
        # Assert
        assert f"audited by {ident}" in message

    def test_the_headline_still_leads(self):
        """The first line is what pytest's short summary shows.

        The identity is a second line on purpose — displacing the rule
        codes would break the triage the codes were added for.
        """
        # Arrange
        ident = "scitex-dev 0.53.0 (/x)"
        # Act
        first = violations_message(
            "sac", "cmd", 1, [_A_FINDING], "", audited_by=ident
        ).splitlines()[0]
        # Assert
        assert first.startswith("audit-all reported violations for 'sac'")


class TestItIsOptional:
    def test_a_violation_report_without_it_still_renders(self):
        """Call sites outside this package build these messages too.

        A required kwarg would replace a real finding with a TypeError
        in a failure formatter — the worst possible place for one.
        """
        # Arrange / nothing to set up
        # Act
        message = violations_message("sac", "cmd", 1, [_A_FINDING], "")
        # Assert
        assert "audited by" not in message

    def test_a_could_not_run_report_without_it_still_renders(self):
        # Arrange / nothing to set up
        # Act
        message = unknown_message("sac", "cmd", 2, ["x"], "")
        # Assert
        assert "audited by" not in message


# EOF
