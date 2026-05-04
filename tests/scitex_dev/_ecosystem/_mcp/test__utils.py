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
    def test_success(self):
        out = run_as_mcp(multiply, a=3, b=4)
        parsed = json.loads(out)
        assert parsed["success"] is True
        assert parsed["data"] == 12

    def test_failure(self):
        out = run_as_mcp(fail_hard)
        parsed = json.loads(out)
        assert parsed["success"] is False
        assert "missing.csv" in parsed["error"]
        assert parsed["error_code"] == "E002"


class TestWrapAsMcp:
    def test_plain_function_success(self):
        def plain_add(a, b):
            return a + b

        out = wrap_as_mcp(plain_add, a=2, b=3)
        parsed = json.loads(out)
        assert parsed["success"] is True
        assert parsed["data"] == 5

    def test_plain_function_failure(self):
        def plain_fail():
            raise ValueError("bad input")

        out = wrap_as_mcp(plain_fail)
        parsed = json.loads(out)
        assert parsed["success"] is False
        assert "bad input" in parsed["error"]
        assert parsed["error_code"] == "E001"

    def test_duck_typed_suggestions(self):
        def fail_with_hints():
            exc = RuntimeError("broke")
            exc.suggestion = "Try again"
            exc.context = {"key": "val"}
            raise exc

        out = wrap_as_mcp(fail_with_hints)
        parsed = json.loads(out)
        assert "Try again" in parsed["hints_on_error"]
        assert parsed["context"]["key"] == "val"


class TestAsyncWrapAsMcp:
    def test_async_success(self):
        import asyncio

        from scitex_dev._ecosystem._mcp._utils import async_wrap_as_mcp

        async def async_add(a, b):
            return a + b

        out = asyncio.run(async_wrap_as_mcp(async_add, a=2, b=3))
        parsed = json.loads(out)
        assert parsed["success"] is True
        assert parsed["data"] == 5

    def test_async_failure(self):
        import asyncio

        from scitex_dev._ecosystem._mcp._utils import async_wrap_as_mcp

        async def async_fail():
            raise FileNotFoundError("missing.csv")

        out = asyncio.run(async_wrap_as_mcp(async_fail))
        parsed = json.loads(out)
        assert parsed["success"] is False
        assert "missing.csv" in parsed["error"]
        assert parsed["error_code"] == "E002"

    def test_async_duck_typed_suggestions(self):
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
    def test_manual_result(self):
        r = Result(success=True, data={"count": 5})
        out = result_to_mcp(r)
        parsed = json.loads(out)
        assert parsed["data"]["count"] == 5
