#!/usr/bin/env python3
"""Tests for scitex_dev._core.cli_utils — handle_result, run_as_cli, wrap_as_cli."""

import io
import json


from scitex_dev._core.cli_utils import handle_result
from scitex_dev._core.types import Result


class TestHandleResult:
    def test_success_prints_data(self):
        buf = io.StringIO()
        r = Result(success=True, data="hello world")
        code = handle_result(r, file=buf)
        assert code == 0
        assert "hello world" in buf.getvalue()

    def test_success_dict_as_json(self):
        buf = io.StringIO()
        r = Result(success=True, data={"key": "val"})
        handle_result(r, file=buf)
        assert '"key"' in buf.getvalue()

    def test_failure_prints_error(self):
        buf = io.StringIO()
        r = Result(success=False, error="something broke", error_code="E999")
        code = handle_result(r, file=buf)
        assert code == 1
        assert "Error: something broke" in buf.getvalue()

    def test_failure_with_hints_on_error(self):
        buf = io.StringIO()
        r = Result(
            success=False,
            error="fail",
            hints_on_error=["Try A", "Try B"],
        )
        handle_result(r, file=buf)
        output = buf.getvalue()
        assert "  - Try A" in output
        assert "  - Try B" in output

    def test_as_json_full_output(self):
        buf = io.StringIO()
        r = Result(success=True, data=42)
        handle_result(r, as_json=True, file=buf)

        parsed = json.loads(buf.getvalue())
        assert parsed["success"] is True
        assert parsed["data"] == 42

    def test_as_json_on_error(self):
        buf = io.StringIO()
        r = Result(success=False, error="err", error_code="E001")
        handle_result(r, as_json=True, file=buf)

        parsed = json.loads(buf.getvalue())
        assert parsed["success"] is False
        assert parsed["error_code"] == "E001"


class TestWrapAsCli:
    def test_success_exits_zero(self):
        import pytest

        from scitex_dev._core.cli_utils import wrap_as_cli

        def add(a, b):
            return a + b

        with pytest.raises(SystemExit) as exc_info:
            wrap_as_cli(add, as_json=False, a=2, b=3)
        assert exc_info.value.code == 0

    def test_failure_exits_nonzero(self):
        import pytest

        from scitex_dev._core.cli_utils import wrap_as_cli

        def fail():
            raise FileNotFoundError("missing.csv")

        with pytest.raises(SystemExit) as exc_info:
            wrap_as_cli(fail, as_json=False)
        assert exc_info.value.code != 0

    def test_json_output_on_success(self, capsys):
        import pytest

        from scitex_dev._core.cli_utils import wrap_as_cli

        def get_data():
            return {"count": 42}

        with pytest.raises(SystemExit):
            wrap_as_cli(get_data, as_json=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["success"] is True
        assert parsed["data"]["count"] == 42

    def test_json_output_on_error(self, capsys):
        import pytest

        from scitex_dev._core.cli_utils import wrap_as_cli

        def fail():
            raise ValueError("bad input")

        with pytest.raises(SystemExit):
            wrap_as_cli(fail, as_json=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["success"] is False
        assert "bad input" in parsed["error"]
        assert parsed["error_code"] == "E001"

    def test_duck_typed_suggestions(self, capsys):
        import pytest

        from scitex_dev._core.cli_utils import wrap_as_cli

        def fail_with_hints():
            exc = RuntimeError("broke")
            exc.suggestion = "Try again"
            raise exc

        with pytest.raises(SystemExit):
            wrap_as_cli(fail_with_hints, as_json=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "Try again" in parsed["hints_on_error"]
