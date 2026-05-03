#!/usr/bin/env python3
"""Tests for scitex_dev.types — Result dataclass."""

import json
from pathlib import Path

from scitex_dev._core.types import Result


class TestResult:
    def test_success_result(self):
        r = Result(success=True, data=42)
        assert r.success is True
        assert r.data == 42
        assert r.error is None

    def test_failure_result(self):
        r = Result(success=False, error="boom", error_code="E001")
        assert r.success is False
        assert r.error == "boom"
        assert r.error_code == "E001"

    def test_to_dict_strips_none(self):
        r = Result(success=True, data="hello")
        d = r.to_dict()
        assert "error" not in d
        assert "error_code" not in d
        assert d["success"] is True
        assert d["data"] == "hello"

    def test_to_dict_keeps_false(self):
        r = Result(success=False, error="err")
        d = r.to_dict()
        assert d["success"] is False
        assert "data" not in d

    def test_to_json_valid(self):
        r = Result(success=True, data={"key": "val"})
        parsed = json.loads(r.to_json())
        assert parsed["success"] is True
        assert parsed["data"]["key"] == "val"

    def test_to_json_handles_path(self):
        r = Result(success=True, data=Path("/tmp"))
        parsed = json.loads(r.to_json())
        assert parsed["data"] == "/tmp"

    def test_exit_code_success(self):
        assert Result(success=True, data="ok").exit_code == 0

    def test_exit_code_validation(self):
        assert Result(success=False, error="bad", error_code="E001").exit_code == 2

    def test_exit_code_permission(self):
        assert Result(success=False, error="denied", error_code="E003").exit_code == 4

    def test_exit_code_unknown(self):
        assert Result(success=False, error="?", error_code="E888").exit_code == 1

    def test_exit_code_no_code(self):
        assert Result(success=False, error="generic").exit_code == 1

    def test_hints_and_side_effects(self):
        r = Result(
            success=True,
            data="done",
            side_effects=["file_create: /tmp/out.csv"],
            hints_on_error=["Run validation"],
        )
        assert len(r.side_effects) == 1
        assert len(r.hints_on_error) == 1

    def test_idempotent_flag(self):
        assert Result(success=True, data="ok", idempotent=True).idempotent is True
