#!/usr/bin/env python3
"""Tests for scitex_dev.cli_utils — handle_result, run_as_cli."""

import io

from scitex_dev.cli_utils import handle_result
from scitex_dev.types import Result


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

    def test_failure_with_next_steps(self):
        buf = io.StringIO()
        r = Result(
            success=False,
            error="fail",
            next_steps=["Try A", "Try B"],
        )
        handle_result(r, file=buf)
        output = buf.getvalue()
        assert "  - Try A" in output
        assert "  - Try B" in output

    def test_as_json_full_output(self):
        buf = io.StringIO()
        r = Result(success=True, data=42)
        handle_result(r, as_json=True, file=buf)
        import json

        parsed = json.loads(buf.getvalue())
        assert parsed["success"] is True
        assert parsed["data"] == 42

    def test_as_json_on_error(self):
        buf = io.StringIO()
        r = Result(success=False, error="err", error_code="E001")
        handle_result(r, as_json=True, file=buf)
        import json

        parsed = json.loads(buf.getvalue())
        assert parsed["success"] is False
        assert parsed["error_code"] == "E001"
