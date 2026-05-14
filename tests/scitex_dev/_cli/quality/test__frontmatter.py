"""Smoke test for scitex_dev._cli.quality._frontmatter."""

from __future__ import annotations

import pytest

from scitex_dev._cli.quality._frontmatter import (
    KNOWN_TAGS,
    audit_frontmatter,
    _estimate_context_tokens,
    _parse_frontmatter,
)


def test_known_tags_nonempty():
    # Arrange
    # Act
    # Assert
    assert "scitex-package" in KNOWN_TAGS


def test_estimate_context_tokens_estimate_context_tokens_0_100():
    # Arrange
    # Act
    # Assert
    assert _estimate_context_tokens(0) == 100


def test_estimate_context_tokens_estimate_context_tokens_40000_round_4000():
    # Arrange
    # Act
    # Assert
    assert _estimate_context_tokens(40_000) == round(40_000 / 4 / 100) * 100


def test_parse_frontmatter_extracts_yaml():
    # Arrange
    # Act
    # Assert
    pytest.importorskip("yaml")
    text = "---\nname: foo\ndescription: bar\n---\n# heading\nbody\n"
    fm = _parse_frontmatter(text)
    assert fm == {"name": "foo", "description": "bar"}


def test_audit_frontmatter_runs_on_empty_dir(tmp_path):
    # Arrange
    # Act
    # Assert
    pytest.importorskip("yaml")
    rc = audit_frontmatter(tmp_path)
    assert rc == 0
