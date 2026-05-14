#!/usr/bin/env python3
"""Tests for scitex_dev.errors — ErrorCode registry and classify_exception."""

import pytest

from scitex_dev._core.errors import ErrorCode, ScitexError, classify_exception


class TestErrorCode:
    def test_all_values_unique(self):
        # Arrange
        # Act
        # Assert
        values = [e.value for e in ErrorCode]
        assert len(values) == len(set(values))

    def test_ok_exit_code(self):
        # Arrange
        # Act
        # Assert
        assert ErrorCode.OK.exit_code == 0

    def test_validation_exit_code(self):
        # Arrange
        # Act
        # Assert
        assert ErrorCode.VALIDATION.exit_code == 2

    def test_permission_exit_code(self):
        # Arrange
        # Act
        # Assert
        assert ErrorCode.PERMISSION.exit_code == 4

    def test_dependency_exit_code(self):
        # Arrange
        # Act
        # Assert
        assert ErrorCode.DEPENDENCY.exit_code == 3

    def test_conflict_exit_code(self):
        # Arrange
        # Act
        # Assert
        assert ErrorCode.CONFLICT.exit_code == 6

    def test_enum_compares_equal_to_string_value_errorcode_ok_e000(self):
        # Arrange
        # Act
        # Assert
        assert ErrorCode.OK == "E000"


    def test_enum_compares_equal_to_string_value_str_errorcode_internal_errorcode_interna(self):
        # Arrange
        # Act
        # Assert
        assert str(ErrorCode.INTERNAL) == "ErrorCode.INTERNAL"


class TestClassifyException:
    def test_file_not_found(self):
        # Arrange
        # Act
        # Assert
        assert classify_exception(FileNotFoundError("x")) == ErrorCode.FILE_NOT_FOUND

    def test_permission_error_maps_to_permission_code(self):
        # Arrange
        # Act
        # Assert
        assert classify_exception(PermissionError("x")) == ErrorCode.PERMISSION

    def test_timeout_error_maps_to_timeout_code(self):
        # Arrange
        # Act
        # Assert
        assert classify_exception(TimeoutError("x")) == ErrorCode.TIMEOUT

    def test_value_error_maps_to_validation_code(self):
        # Arrange
        # Act
        # Assert
        assert classify_exception(ValueError("x")) == ErrorCode.VALIDATION

    def test_import_error_maps_to_dependency_code(self):
        # Arrange
        # Act
        # Assert
        assert classify_exception(ImportError("x")) == ErrorCode.DEPENDENCY

    def test_connection_error_maps_to_network_code(self):
        # Arrange
        # Act
        # Assert
        assert classify_exception(ConnectionError("x")) == ErrorCode.NETWORK

    def test_key_error_maps_to_config_code(self):
        # Arrange
        # Act
        # Assert
        assert classify_exception(KeyError("x")) == ErrorCode.CONFIG

    def test_unknown_falls_to_internal(self):
        # Arrange
        # Act
        # Assert
        assert classify_exception(RuntimeError("x")) == ErrorCode.INTERNAL

    def test_duck_typed_error_code_string(self):
        # Arrange
        # Act
        # Assert
        exc = Exception("test")
        exc.error_code = "E003"
        assert classify_exception(exc) == ErrorCode.PERMISSION

    def test_duck_typed_error_code_enum(self):
        # Arrange
        # Act
        # Assert
        exc = Exception("test")
        exc.error_code = ErrorCode.TIMEOUT
        assert classify_exception(exc) == ErrorCode.TIMEOUT

    def test_duck_typed_invalid_code_falls_through(self):
        # Arrange
        # Act
        # Assert
        exc = ValueError("test")
        exc.error_code = "INVALID"
        assert classify_exception(exc) == ErrorCode.VALIDATION


class TestScitexError:
    def test_default_code_is_internal_err_error_code_errorcode_internal(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError("boom")
        assert err.error_code == ErrorCode.INTERNAL


    def test_default_code_is_internal_err_message_boom(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError("boom")
        assert err.message == "boom"


    def test_default_code_is_internal_err_remediation_is_none(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError("boom")
        assert err.remediation is None

    def test_explicit_code_and_remediation_err_error_code_errorcode_dependency(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError(
            "h5py not installed",
            code=ErrorCode.DEPENDENCY,
            remediation="pip install scitex-io[h5]",
        )
        assert err.error_code == ErrorCode.DEPENDENCY


    def test_explicit_code_and_remediation_err_remediation_pip_install_scitex_io_h5(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError(
            "h5py not installed",
            code=ErrorCode.DEPENDENCY,
            remediation="pip install scitex-io[h5]",
        )
        assert err.remediation == "pip install scitex-io[h5]"

    def test_scitex_error_is_raisable_exception(self):
        # Arrange
        # Act
        # Assert
        with pytest.raises(ScitexError):
            raise ScitexError("x", code=ErrorCode.VALIDATION)

    def test_to_dict_minimal(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError("bad", code=ErrorCode.VALIDATION)
        assert err.to_dict() == {"code": "E001", "message": "bad"}

    def test_to_dict_with_remediation(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError(
            "missing", code=ErrorCode.DEPENDENCY, remediation="pip install x"
        )
        assert err.to_dict() == {
            "code": "E004",
            "message": "missing",
            "remediation": "pip install x",
        }

    def test_str_includes_code(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError("boom", code=ErrorCode.NETWORK)
        assert str(err) == "[E007] boom"

    def test_str_includes_remediation_fix_it_in_str_err(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError("boom", code=ErrorCode.DEPENDENCY, remediation="fix it")
        assert "fix it" in str(err)


    def test_str_includes_remediation_e004_in_str_err(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError("boom", code=ErrorCode.DEPENDENCY, remediation="fix it")
        assert "[E004]" in str(err)

    def test_classify_exception_picks_up_scitex_error(self):
        # Arrange
        # Act
        # Assert
        err = ScitexError("x", code=ErrorCode.RATE_LIMITED)
        assert classify_exception(err) == ErrorCode.RATE_LIMITED

    def test_chaining_preserves_cause(self):
        # Arrange
        # Act
        # Assert
        try:
            try:
                raise ImportError("h5py")
            except ImportError as e:
                raise ScitexError(
                    "h5py not installed",
                    code=ErrorCode.DEPENDENCY,
                    remediation="pip install scitex-io[h5]",
                ) from e
        except ScitexError as e:
            assert isinstance(e.__cause__, ImportError)

    def test_top_level_reexport_re_code_is_errorcode(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev import ErrorCode as RE_Code
        from scitex_dev import ScitexError as RE_Err

        assert RE_Code is ErrorCode


    def test_top_level_reexport_re_err_is_scitexerror(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev import ErrorCode as RE_Code
        from scitex_dev import ScitexError as RE_Err

        assert RE_Err is ScitexError
