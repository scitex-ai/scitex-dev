#!/usr/bin/env python3
"""Tests for scitex_dev.decorators — @supports_return_as."""

from scitex_dev._core.decorators import supports_return_as
from scitex_dev._core.types import Result


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
        # Arrange
        # Act
        # Assert
        assert add(1, 2) == 3

    def test_return_as_result_success_isinstance_r_result(self):
        # Arrange
        # Act
        # Assert
        r = add(1, 2, return_as="result")
        assert isinstance(r, Result)


    def test_return_as_result_success_r_success_is_true(self):
        # Arrange
        # Act
        # Assert
        r = add(1, 2, return_as="result")
        assert r.success is True


    def test_return_as_result_success_r_data_3(self):
        # Arrange
        # Act
        # Assert
        r = add(1, 2, return_as="result")
        assert r.data == 3

    def test_return_as_result_failure_isinstance_r_result(self):
        # Arrange
        # Act
        # Assert
        r = fail_validation("bad", return_as="result")
        assert isinstance(r, Result)


    def test_return_as_result_failure_r_success_is_false(self):
        # Arrange
        # Act
        # Assert
        r = fail_validation("bad", return_as="result")
        assert r.success is False


    def test_return_as_result_failure_invalid_bad_in_r_error(self):
        # Arrange
        # Act
        # Assert
        r = fail_validation("bad", return_as="result")
        assert "Invalid: bad" in r.error


    def test_return_as_result_failure_r_error_code_e001(self):
        # Arrange
        # Act
        # Assert
        r = fail_validation("bad", return_as="result")
        assert r.error_code == "E001"  # ValueError -> VALIDATION

    def test_exception_without_return_as_raises(self):
        # Arrange
        # Act
        # Assert
        try:
            fail_validation("bad")
            assert False, "Should have raised"
        except ValueError:
            pass

    def test_passthrough_other_return_as(self):
        # Arrange
        # Act
        # Assert
        assert format_data("hello", return_as="upper") == "HELLO"

    def test_duck_typed_suggestion_r_success_is_false(self):
        # Arrange
        # Act
        # Assert
        r = fail_with_suggestion("x", return_as="result")
        assert r.success is False


    def test_duck_typed_suggestion_try_restarting_in_r_hints_on_error(self):
        # Arrange
        # Act
        # Assert
        r = fail_with_suggestion("x", return_as="result")
        assert "Try restarting" in r.hints_on_error


    def test_duck_typed_suggestion_check_logs_in_r_hints_on_error(self):
        # Arrange
        # Act
        # Assert
        r = fail_with_suggestion("x", return_as="result")
        assert "Check logs" in r.hints_on_error


    def test_duck_typed_suggestion_r_context_input_x(self):
        # Arrange
        # Act
        # Assert
        r = fail_with_suggestion("x", return_as="result")
        assert r.context == {"input": "x"}

    def test_preserves_wrapped_function_name(self):
        # Arrange
        # Act
        # Assert
        assert add.__name__ == "add"

    def test_preserves_wrapped_function_docstring(self):
        # Arrange
        # Act
        # Assert
        assert add.__doc__ == "Add two numbers."
