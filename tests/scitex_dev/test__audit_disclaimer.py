#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the audit-footer self-reference (scitex_dev._audit_disclaimer).

The escalation footer's issue-tracker URL is derived from the ecosystem
registry's own ``scitex-dev`` entry, so the org migration
(ywatanabe1989 -> scitex-ai) cannot leave a stale hardcode behind.
No network access.
"""

from __future__ import annotations

from scitex_dev._audit_disclaimer import _issues_url, _skill_hints_text
from scitex_dev._ecosystem._registry import ECOSYSTEM


def test_issues_url_is_derived_from_registry_entry():
    # Arrange
    repo = ECOSYSTEM["scitex-dev"]["github_repo"]
    # Act
    url = _issues_url()
    # Assert
    assert url == f"https://github.com/{repo}/issues/new"


def test_skill_hints_footer_points_at_scitex_ai_issue_tracker():
    # Arrange
    expected = "https://github.com/scitex-ai/scitex-dev/issues/new"
    # Act
    text = _skill_hints_text()
    # Assert
    assert expected in text


def test_skill_hints_footer_has_no_stale_owner_reference():
    # Arrange
    stale = "ywatanabe1989"
    # Act
    text = _skill_hints_text()
    # Assert
    assert stale not in text
