#!/usr/bin/env python3
"""Tests for scitex_dev.decorators — @supports_return_as."""

from scitex_dev.decorators import supports_return_as
from scitex_dev.types import Result


@supports_return_as
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@supports_return_as
def fail_validation(x):
    raise ValueError(f"Invalid: {x}")


@supports_return_as
def fail_with_suggestion(x):
    exc = RuntimeError("Something broke")
    exc.suggestion = "Try restarting"
    exc.suggestions = ["Check logs", "File a bug"]
    exc.context = {"input": x}
    raise exc


@supports_return_as
def format_data(data, return_as=None):
    """Function that already has return_as for format selection."""
    if return_as == "upper":
        return data.upper()
    return data


class TestSupportsReturnAs:
    def test_no_return_as_returns_raw(self):
        assert add(1, 2) == 3

    def test_return_as_result_success(self):
        r = add(1, 2, return_as="result")
        assert isinstance(r, Result)
        assert r.success is True
        assert r.data == 3

    def test_return_as_result_failure(self):
        r = fail_validation("bad", return_as="result")
        assert isinstance(r, Result)
        assert r.success is False
        assert "Invalid: bad" in r.error
        assert r.error_code == "E001"  # ValueError -> VALIDATION

    def test_exception_without_return_as_raises(self):
        try:
            fail_validation("bad")
            assert False, "Should have raised"
        except ValueError:
            pass

    def test_passthrough_other_return_as(self):
        assert format_data("hello", return_as="upper") == "HELLO"

    def test_duck_typed_suggestion(self):
        r = fail_with_suggestion("x", return_as="result")
        assert r.success is False
        assert "Try restarting" in r.next_steps
        assert "Check logs" in r.next_steps
        assert r.context == {"input": "x"}

    def test_preserves_name(self):
        assert add.__name__ == "add"

    def test_preserves_doc(self):
        assert add.__doc__ == "Add two numbers."
