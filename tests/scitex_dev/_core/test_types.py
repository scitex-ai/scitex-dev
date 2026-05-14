#!/usr/bin/env python3
"""Tests for scitex_dev.types — Result dataclass."""

import json
from pathlib import Path

from scitex_dev._core.types import Result


class TestResult:
    def test_success_result_has_data_and_no_error_r_success_is_true(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data=42)
        assert r.success is True


    def test_success_result_has_data_and_no_error_r_data_42(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data=42)
        assert r.data == 42


    def test_success_result_has_data_and_no_error_r_error_is_none(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data=42)
        assert r.error is None

    def test_failure_result_records_error_and_code_r_success_is_false(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=False, error="boom", error_code="E001")
        assert r.success is False


    def test_failure_result_records_error_and_code_r_error_boom(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=False, error="boom", error_code="E001")
        assert r.error == "boom"


    def test_failure_result_records_error_and_code_r_error_code_e001(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=False, error="boom", error_code="E001")
        assert r.error_code == "E001"

    def test_to_dict_strips_none_error_not_in_d(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data="hello")
        d = r.to_dict()
        assert "error" not in d


    def test_to_dict_strips_none_error_code_not_in_d(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data="hello")
        d = r.to_dict()
        assert "error_code" not in d


    def test_to_dict_strips_none_d_success_is_true(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data="hello")
        d = r.to_dict()
        assert d["success"] is True


    def test_to_dict_strips_none_d_data_hello(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data="hello")
        d = r.to_dict()
        assert d["data"] == "hello"

    def test_to_dict_keeps_false_d_success_is_false(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=False, error="err")
        d = r.to_dict()
        assert d["success"] is False


    def test_to_dict_keeps_false_data_not_in_d(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=False, error="err")
        d = r.to_dict()
        assert "data" not in d

    def test_to_json_valid_parsed_success_is_true(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data={"key": "val"})
        parsed = json.loads(r.to_json())
        assert parsed["success"] is True


    def test_to_json_valid_parsed_data_key_val(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data={"key": "val"})
        parsed = json.loads(r.to_json())
        assert parsed["data"]["key"] == "val"

    def test_to_json_handles_path(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data=Path("/tmp"))
        parsed = json.loads(r.to_json())
        assert parsed["data"] == "/tmp"

    def test_exit_code_success(self):
        # Arrange
        # Act
        # Assert
        assert Result(success=True, data="ok").exit_code == 0

    def test_exit_code_validation(self):
        # Arrange
        # Act
        # Assert
        assert Result(success=False, error="bad", error_code="E001").exit_code == 2

    def test_exit_code_permission(self):
        # Arrange
        # Act
        # Assert
        assert Result(success=False, error="denied", error_code="E003").exit_code == 4

    def test_exit_code_unknown(self):
        # Arrange
        # Act
        # Assert
        assert Result(success=False, error="?", error_code="E888").exit_code == 1

    def test_exit_code_no_code(self):
        # Arrange
        # Act
        # Assert
        assert Result(success=False, error="generic").exit_code == 1

    def test_hints_and_side_effects_len_r_side_effects_1(self):
        # Arrange
        # Act
        # Assert
        r = Result(
            success=True,
            data="done",
            side_effects=["file_create: /tmp/out.csv"],
            hints_on_error=["Run validation"],
        )
        assert len(r.side_effects) == 1


    def test_hints_and_side_effects_len_r_hints_on_error_1(self):
        # Arrange
        # Act
        # Assert
        r = Result(
            success=True,
            data="done",
            side_effects=["file_create: /tmp/out.csv"],
            hints_on_error=["Run validation"],
        )
        assert len(r.hints_on_error) == 1

    def test_idempotent_flag_is_stored_on_result(self):
        # Arrange
        # Act
        # Assert
        assert Result(success=True, data="ok", idempotent=True).idempotent is True
