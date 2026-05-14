#!/usr/bin/env python3
"""Tests for scitex_dev._core.cli_utils — handle_result, run_as_cli, wrap_as_cli."""

import io
import json

import pytest

from scitex_dev._core.cli_utils import handle_result
from scitex_dev._core.types import Result


class TestHandleResult:
    def test_success_prints_data_code_0(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(success=True, data="hello world")
        code = handle_result(r, file=buf)
        assert code == 0

    def test_success_prints_data_hello_world_in_buf_getvalue(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(success=True, data="hello world")
        code = handle_result(r, file=buf)
        assert "hello world" in buf.getvalue()

    def test_success_dict_as_json(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(success=True, data={"key": "val"})
        handle_result(r, file=buf)
        assert '"key"' in buf.getvalue()

    def test_failure_prints_error_code_1(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(success=False, error="something broke", error_code="E999")
        code = handle_result(r, file=buf)
        assert code == 1

    def test_failure_prints_error_error_something_broke_in_buf_getvalue(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(success=False, error="something broke", error_code="E999")
        code = handle_result(r, file=buf)
        assert "Error: something broke" in buf.getvalue()

    def test_failure_with_hints_on_error_try_a_in_output(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(
            success=False,
            error="fail",
            hints_on_error=["Try A", "Try B"],
        )
        handle_result(r, file=buf)
        output = buf.getvalue()
        assert "  - Try A" in output

    def test_failure_with_hints_on_error_try_b_in_output(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(
            success=False,
            error="fail",
            hints_on_error=["Try A", "Try B"],
        )
        handle_result(r, file=buf)
        output = buf.getvalue()
        assert "  - Try B" in output

    def test_as_json_full_output_parsed_success_is_true(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(success=True, data=42)
        handle_result(r, as_json=True, file=buf)

        parsed = json.loads(buf.getvalue())
        assert parsed["success"] is True

    def test_as_json_full_output_parsed_data_42(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(success=True, data=42)
        handle_result(r, as_json=True, file=buf)

        parsed = json.loads(buf.getvalue())
        assert parsed["data"] == 42

    def test_as_json_on_error_parsed_success_is_false(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(success=False, error="err", error_code="E001")
        handle_result(r, as_json=True, file=buf)

        parsed = json.loads(buf.getvalue())
        assert parsed["success"] is False

    def test_as_json_on_error_parsed_error_code_e001(self):
        # Arrange
        # Act
        # Assert
        buf = io.StringIO()
        r = Result(success=False, error="err", error_code="E001")
        handle_result(r, as_json=True, file=buf)

        parsed = json.loads(buf.getvalue())
        assert parsed["error_code"] == "E001"


class TestWrapAsCli:
    def test_success_path_exit_code_is_zero(self):
        # Arrange
        from scitex_dev._core.cli_utils import wrap_as_cli

        def add(a, b):
            return a + b

        # Act
        try:
            wrap_as_cli(add, as_json=False, a=2, b=3)
            code = None
        except SystemExit as e:
            code = e.code
        # Assert
        assert code == 0

    def test_failure_path_exit_code_is_nonzero(self):
        # Arrange
        from scitex_dev._core.cli_utils import wrap_as_cli

        def fail():
            raise FileNotFoundError("missing.csv")

        # Act
        try:
            wrap_as_cli(fail, as_json=False)
            code = 0
        except SystemExit as e:
            code = e.code
        # Assert
        assert code != 0

    @pytest.fixture
    def _json_success_payload(self, capsys):
        import pytest

        from scitex_dev._core.cli_utils import wrap_as_cli

        def get_data():
            return {"count": 42}

        with pytest.raises(SystemExit):
            wrap_as_cli(get_data, as_json=True)
        captured = capsys.readouterr()
        return json.loads(captured.out)

    def test_json_output_on_success_success_is_true(self, _json_success_payload):
        # Arrange
        parsed = _json_success_payload
        # Act
        success = parsed["success"]
        # Assert
        assert success is True

    def test_json_output_on_success_data_count_is_42(self, _json_success_payload):
        # Arrange
        parsed = _json_success_payload
        # Act
        count = parsed["data"]["count"]
        # Assert
        assert count == 42

    @pytest.fixture
    def _json_error_payload(self, capsys):
        import pytest

        from scitex_dev._core.cli_utils import wrap_as_cli

        def fail():
            raise ValueError("bad input")

        with pytest.raises(SystemExit):
            wrap_as_cli(fail, as_json=True)
        captured = capsys.readouterr()
        return json.loads(captured.out)

    def test_json_output_on_error_success_is_false(self, _json_error_payload):
        # Arrange
        parsed = _json_error_payload
        # Act
        success = parsed["success"]
        # Assert
        assert success is False

    def test_json_output_on_error_message_contains_bad_input(self, _json_error_payload):
        # Arrange
        parsed = _json_error_payload
        # Act
        msg = parsed["error"]
        # Assert
        assert "bad input" in msg

    def test_json_output_on_error_error_code_is_e001(self, _json_error_payload):
        # Arrange
        parsed = _json_error_payload
        # Act
        code = parsed["error_code"]
        # Assert
        assert code == "E001"

    def test_duck_typed_suggestions_propagated_to_hints(self, capsys):
        # Arrange
        from scitex_dev._core.cli_utils import wrap_as_cli

        def fail_with_hints():
            exc = RuntimeError("broke")
            exc.suggestion = "Try again"
            raise exc

        try:
            wrap_as_cli(fail_with_hints, as_json=True)
        except SystemExit:
            pass
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        # Act
        hints = parsed["hints_on_error"]
        # Assert
        assert "Try again" in hints
