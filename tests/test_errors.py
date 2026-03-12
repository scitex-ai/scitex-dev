#!/usr/bin/env python3
"""Tests for scitex_dev.errors — ErrorCode registry and classify_exception."""

from scitex_dev.errors import ErrorCode, classify_exception


class TestErrorCode:
    def test_all_values_unique(self):
        values = [e.value for e in ErrorCode]
        assert len(values) == len(set(values))

    def test_ok_exit_code(self):
        assert ErrorCode.OK.exit_code == 0

    def test_validation_exit_code(self):
        assert ErrorCode.VALIDATION.exit_code == 2

    def test_permission_exit_code(self):
        assert ErrorCode.PERMISSION.exit_code == 4

    def test_dependency_exit_code(self):
        assert ErrorCode.DEPENDENCY.exit_code == 3

    def test_conflict_exit_code(self):
        assert ErrorCode.CONFLICT.exit_code == 6

    def test_string_behavior(self):
        assert ErrorCode.OK == "E000"
        assert str(ErrorCode.INTERNAL) == "ErrorCode.INTERNAL"


class TestClassifyException:
    def test_file_not_found(self):
        assert classify_exception(FileNotFoundError("x")) == ErrorCode.FILE_NOT_FOUND

    def test_permission_error(self):
        assert classify_exception(PermissionError("x")) == ErrorCode.PERMISSION

    def test_timeout_error(self):
        assert classify_exception(TimeoutError("x")) == ErrorCode.TIMEOUT

    def test_value_error(self):
        assert classify_exception(ValueError("x")) == ErrorCode.VALIDATION

    def test_import_error(self):
        assert classify_exception(ImportError("x")) == ErrorCode.DEPENDENCY

    def test_connection_error(self):
        assert classify_exception(ConnectionError("x")) == ErrorCode.NETWORK

    def test_key_error(self):
        assert classify_exception(KeyError("x")) == ErrorCode.CONFIG

    def test_unknown_falls_to_internal(self):
        assert classify_exception(RuntimeError("x")) == ErrorCode.INTERNAL

    def test_duck_typed_error_code_string(self):
        exc = Exception("test")
        exc.error_code = "E003"
        assert classify_exception(exc) == ErrorCode.PERMISSION

    def test_duck_typed_error_code_enum(self):
        exc = Exception("test")
        exc.error_code = ErrorCode.TIMEOUT
        assert classify_exception(exc) == ErrorCode.TIMEOUT

    def test_duck_typed_invalid_code_falls_through(self):
        exc = ValueError("test")
        exc.error_code = "INVALID"
        assert classify_exception(exc) == ErrorCode.VALIDATION
