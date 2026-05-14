#!/usr/bin/env python3
"""Tests for scitex_dev._ecosystem._mcp._utils — run_as_mcp, result_to_mcp."""

import json

from scitex_dev._core.decorators import supports_return_as
from scitex_dev._ecosystem._mcp._utils import result_to_mcp, run_as_mcp, wrap_as_mcp
from scitex_dev._core.types import Result


@supports_return_as
def multiply(a: int, b: int) -> int:
    return a * b


@supports_return_as
def fail_hard():
    raise FileNotFoundError("missing.csv")


class TestRunAsMcp:
    def test_success_returns_json_with_data_parsed_success_is_true(self):
        # Arrange
        # Act
        # Assert
        out = run_as_mcp(multiply, a=3, b=4)
        parsed = json.loads(out)
        assert parsed["success"] is True


    def test_success_returns_json_with_data_parsed_data_12(self):
        # Arrange
        # Act
        # Assert
        out = run_as_mcp(multiply, a=3, b=4)
        parsed = json.loads(out)
        assert parsed["data"] == 12

    def test_failure_returns_json_with_error_code_parsed_success_is_false(self):
        # Arrange
        # Act
        # Assert
        out = run_as_mcp(fail_hard)
        parsed = json.loads(out)
        assert parsed["success"] is False


    def test_failure_returns_json_with_error_code_missing_csv_in_parsed_error(self):
        # Arrange
        # Act
        # Assert
        out = run_as_mcp(fail_hard)
        parsed = json.loads(out)
        assert "missing.csv" in parsed["error"]


    def test_failure_returns_json_with_error_code_parsed_error_code_e002(self):
        # Arrange
        # Act
        # Assert
        out = run_as_mcp(fail_hard)
        parsed = json.loads(out)
        assert parsed["error_code"] == "E002"


class TestWrapAsMcp:
    def test_plain_function_success_parsed_success_is_true(self):
        # Arrange
        # Act
        # Assert
        def plain_add(a, b):
            return a + b

        out = wrap_as_mcp(plain_add, a=2, b=3)
        parsed = json.loads(out)
        assert parsed["success"] is True


    def test_plain_function_success_parsed_data_5(self):
        # Arrange
        # Act
        # Assert
        def plain_add(a, b):
            return a + b

        out = wrap_as_mcp(plain_add, a=2, b=3)
        parsed = json.loads(out)
        assert parsed["data"] == 5

    def test_plain_function_failure_parsed_success_is_false(self):
        # Arrange
        # Act
        # Assert
        def plain_fail():
            raise ValueError("bad input")

        out = wrap_as_mcp(plain_fail)
        parsed = json.loads(out)
        assert parsed["success"] is False


    def test_plain_function_failure_bad_input_in_parsed_error(self):
        # Arrange
        # Act
        # Assert
        def plain_fail():
            raise ValueError("bad input")

        out = wrap_as_mcp(plain_fail)
        parsed = json.loads(out)
        assert "bad input" in parsed["error"]


    def test_plain_function_failure_parsed_error_code_e001(self):
        # Arrange
        # Act
        # Assert
        def plain_fail():
            raise ValueError("bad input")

        out = wrap_as_mcp(plain_fail)
        parsed = json.loads(out)
        assert parsed["error_code"] == "E001"

    def test_duck_typed_suggestions_try_again_in_parsed_hints_on_error(self):
        # Arrange
        # Act
        # Assert
        def fail_with_hints():
            exc = RuntimeError("broke")
            exc.suggestion = "Try again"
            exc.context = {"key": "val"}
            raise exc

        out = wrap_as_mcp(fail_with_hints)
        parsed = json.loads(out)
        assert "Try again" in parsed["hints_on_error"]


    def test_duck_typed_suggestions_parsed_context_key_val(self):
        # Arrange
        # Act
        # Assert
        def fail_with_hints():
            exc = RuntimeError("broke")
            exc.suggestion = "Try again"
            exc.context = {"key": "val"}
            raise exc

        out = wrap_as_mcp(fail_with_hints)
        parsed = json.loads(out)
        assert parsed["context"]["key"] == "val"


class TestAsyncWrapAsMcp:
    def test_async_success_returns_json_with_data_parsed_success_is_true(self):
        # Arrange
        # Act
        # Assert
        import asyncio

        from scitex_dev._ecosystem._mcp._utils import async_wrap_as_mcp

        async def async_add(a, b):
            return a + b

        out = asyncio.run(async_wrap_as_mcp(async_add, a=2, b=3))
        parsed = json.loads(out)
        assert parsed["success"] is True


    def test_async_success_returns_json_with_data_parsed_data_5(self):
        # Arrange
        # Act
        # Assert
        import asyncio

        from scitex_dev._ecosystem._mcp._utils import async_wrap_as_mcp

        async def async_add(a, b):
            return a + b

        out = asyncio.run(async_wrap_as_mcp(async_add, a=2, b=3))
        parsed = json.loads(out)
        assert parsed["data"] == 5

    def test_async_failure_returns_json_with_error_code_parsed_success_is_false(self):
        # Arrange
        # Act
        # Assert
        import asyncio

        from scitex_dev._ecosystem._mcp._utils import async_wrap_as_mcp

        async def async_fail():
            raise FileNotFoundError("missing.csv")

        out = asyncio.run(async_wrap_as_mcp(async_fail))
        parsed = json.loads(out)
        assert parsed["success"] is False


    def test_async_failure_returns_json_with_error_code_missing_csv_in_parsed_error(self):
        # Arrange
        # Act
        # Assert
        import asyncio

        from scitex_dev._ecosystem._mcp._utils import async_wrap_as_mcp

        async def async_fail():
            raise FileNotFoundError("missing.csv")

        out = asyncio.run(async_wrap_as_mcp(async_fail))
        parsed = json.loads(out)
        assert "missing.csv" in parsed["error"]


    def test_async_failure_returns_json_with_error_code_parsed_error_code_e002(self):
        # Arrange
        # Act
        # Assert
        import asyncio

        from scitex_dev._ecosystem._mcp._utils import async_wrap_as_mcp

        async def async_fail():
            raise FileNotFoundError("missing.csv")

        out = asyncio.run(async_wrap_as_mcp(async_fail))
        parsed = json.loads(out)
        assert parsed["error_code"] == "E002"

    def test_async_duck_typed_suggestions(self):
        # Arrange
        # Act
        # Assert
        import asyncio

        from scitex_dev._ecosystem._mcp._utils import async_wrap_as_mcp

        async def async_fail_hints():
            exc = RuntimeError("broke")
            exc.suggestion = "Retry"
            raise exc

        out = asyncio.run(async_wrap_as_mcp(async_fail_hints))
        parsed = json.loads(out)
        assert "Retry" in parsed["hints_on_error"]


class TestResultToMcp:
    def test_manual_result_serializes_to_json(self):
        # Arrange
        # Act
        # Assert
        r = Result(success=True, data={"count": 5})
        out = result_to_mcp(r)
        parsed = json.loads(out)
        assert parsed["data"]["count"] == 5
