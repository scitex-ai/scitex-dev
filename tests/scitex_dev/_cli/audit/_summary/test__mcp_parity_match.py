"""Tests for `_mcp_parity_match` — pure §6 name comparison.

The older `<verb>_<api>` (#82) cases live in `test__mcp_parity.py`; this
file covers the mirror `<api>_<noun>` form and the baseline switch.
"""

from __future__ import annotations

import pytest

from scitex_dev._cli.audit._summary._mcp_parity_baseline import ParityBaseline
from scitex_dev._cli.audit._summary._mcp_parity_match import (
    _parity_violations,
    _tool_matches_api,
    missing_python_apis,
)


class TestApiNounForm:
    @pytest.mark.parametrize(
        ("tool", "api"),
        [("describe_data", "describe"), ("verify_result", "verify")],
    )
    def test_single_token_api_section_two_rejects_matches_api_noun_tool(
        self, tool, api
    ):
        # Arrange
        pair = (tool, api)
        # Act
        matched = _tool_matches_api(*pair)
        # Assert
        assert matched is True

    def test_verb_section_two_accepts_bare_does_not_match_api_noun_tool(self):
        # Arrange: `save` is a valid bare tool name, so `save_data` must not
        # stand in for the API `save` — its tool can carry the bare name.
        tool, api = "save_data", "save"
        # Act
        matched = _tool_matches_api(tool, api)
        # Assert
        assert matched is False

    def test_multi_token_api_does_not_match_by_prefix(self):
        # Arrange
        tool, api = "run_test_batch", "run_test"
        # Act
        matched = _tool_matches_api(tool, api)
        # Assert
        assert matched is False

    def test_prefix_needs_an_underscore_boundary(self):
        # Arrange
        tool, api = "describer", "describe"
        # Act
        matched = _tool_matches_api(tool, api)
        # Assert
        assert matched is False

    def test_api_noun_tool_is_not_an_orphan(self):
        # Arrange
        py_apis = {"describe", "verify", "a_b", "c_d", "e_f"}
        tools = {"describe_data", "verify_result", "a_b", "c_d", "e_f"}
        # Act
        violations = _parity_violations("pkg", py_apis, tools)
        # Assert
        assert violations == []


class TestBaselineSwitch:
    def test_baseline_replaces_majority_threshold(self, tmp_path):
        # Arrange: 3/4 missing would trip the threshold without a baseline.
        py_apis = {"a_x", "b_x", "c_x", "d_x"}
        tools = {"a_x"}
        baseline = ParityBaseline(
            path=tmp_path / "b.yaml", missing=frozenset({"b_x", "c_x", "d_x"})
        )
        # Act
        violations = _parity_violations("pkg", py_apis, tools, baseline)
        # Assert
        assert violations == []

    def test_baseline_is_exact_even_below_threshold(self, tmp_path):
        # Arrange: 1/4 missing passes without a baseline but is NEW here.
        py_apis = {"a_x", "b_x", "c_x", "d_x"}
        tools = {"a_x", "b_x", "c_x"}
        baseline = ParityBaseline(path=tmp_path / "b.yaml", missing=frozenset())
        # Act
        violations = _parity_violations("pkg", py_apis, tools, baseline)
        # Assert
        assert [v.rule for v in violations] == ["§6"]

    def test_missing_python_apis_lists_uncovered_names(self):
        # Arrange
        py_apis = {"describe", "run_test", "plot"}
        tools = {"describe_data", "run_test"}
        # Act
        missing = missing_python_apis(py_apis, tools)
        # Assert
        assert missing == {"plot"}
