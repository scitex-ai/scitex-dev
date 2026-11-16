"""Tests for the file-level ``# stx-allow-file: <IDS> (reason: ...)`` pragma.

Instrumentation / measurement scripts must legitimately NOT be
``@stx.session`` scripts (they would record themselves into the store they
measure). STX-S001 is emitted at line 1 with no source line, so the
line-level ``# stx-allow`` cannot reach it; the file-level pragma can — but
only with a written reason, and every applied exemption is reported.

The end-to-end cases use STX-S002 (missing ``__main__`` guard) because it
has no ``requires=`` gate and therefore emits in every environment.
"""

import json

from scitex_dev.linter._cmd_check import _do_check
from scitex_dev.linter._exemptions import scan_file_exemptions
from scitex_dev.linter.checker import lint_source
from scitex_dev.linter.config import LinterConfig

_NO_GUARD_BODY = '"""Measure the store."""\n\nimport sqlite3\n\nX = sqlite3\n'


def _ids(source: str, filepath: str = "bench_store.py") -> list:
    return sorted(
        i.rule.id for i in lint_source(source, filepath=filepath, config=LinterConfig())
    )


# --------------------------------------------------------------------------- #
# Applied exemptions                                                          #
# --------------------------------------------------------------------------- #


def test_baseline_file_without_guard_emits_s002():
    # Arrange
    src = _NO_GUARD_BODY
    # Act
    ids = _ids(src)
    # Assert
    assert "STX-S002" in ids


def test_header_comment_pragma_with_reason_suppresses_s002():
    # Arrange
    src = (
        "#!/usr/bin/env python3\n"
        "# stx-allow-file: STX-S002  (reason: imported by the bench harness)\n"
        + _NO_GUARD_BODY
    )
    # Act
    ids = _ids(src)
    # Assert
    assert ids == []


def test_docstring_line_pragma_with_reason_suppresses_s002():
    # Arrange
    src = (
        '"""Measure the store.\n'
        "\n"
        "stx-allow-file: STX-S002  (reason: instrumentation, imported not run)\n"
        '"""\n'
        "\n"
        "X = 1\n"
    )
    # Act
    ids = _ids(src)
    # Assert
    assert ids == []


def test_pragma_records_ids_reason_and_line():
    # Arrange
    src = "# stx-allow-file: STX-S001, STX-S002  (reason: a (nested) why)\nX = 1\n"
    # Act
    scan = scan_file_exemptions(src)
    # Assert
    assert [e.to_dict() for e in scan.exemptions] == [
        {"rules": ["STX-S001", "STX-S002"], "reason": "a (nested) why", "line": 1}
    ]


def test_pragma_only_exempts_the_named_rule():
    # Arrange — exempting S003 must not hide the S002 finding.
    src = "# stx-allow-file: STX-S003  (reason: unrelated)\n" + _NO_GUARD_BODY
    # Act
    ids = _ids(src)
    # Assert
    assert ids == ["STX-S002"]


# --------------------------------------------------------------------------- #
# Rejected pragmas -> STX-EX001, NOT applied                                  #
# --------------------------------------------------------------------------- #


def test_pragma_without_reason_is_rejected_with_ex001():
    # Arrange
    src = "# stx-allow-file: STX-S002\n" + _NO_GUARD_BODY
    # Act
    ids = _ids(src)
    # Assert
    assert ids == ["STX-EX001", "STX-S002"]


def test_pragma_with_empty_reason_is_rejected_with_ex001():
    # Arrange
    src = "# stx-allow-file: STX-S002 (reason:   )\n" + _NO_GUARD_BODY
    # Act
    ids = _ids(src)
    # Assert
    assert ids == ["STX-EX001", "STX-S002"]


def test_pragma_without_rule_ids_is_rejected_with_ex001():
    # Arrange
    src = "# stx-allow-file: (reason: everything)\n" + _NO_GUARD_BODY
    # Act
    ids = _ids(src)
    # Assert
    assert ids == ["STX-EX001", "STX-S002"]


def test_pragma_with_unknown_rule_id_is_rejected_with_ex001():
    # Arrange
    src = "# stx-allow-file: STX-ZZ999 (reason: typo)\n" + _NO_GUARD_BODY
    # Act
    ids = _ids(src)
    # Assert
    assert ids == ["STX-EX001", "STX-S002"]


def test_pragma_on_testing_rule_is_rejected_with_ex001():
    # Arrange — no-mocks forbids suppression; a file pragma must not defeat it.
    src = "# stx-allow-file: STX-NM001 (reason: legacy)\nX = 1\n"
    # Act
    scan = scan_file_exemptions(src)
    # Assert
    assert (scan.exemptions, len(scan.problems)) == ([], 1)


def test_pragma_after_first_statement_is_rejected_with_ex001():
    # Arrange
    src = _NO_GUARD_BODY + "# stx-allow-file: STX-S002 (reason: too late)\n"
    # Act
    ids = _ids(src)
    # Assert
    assert ids == ["STX-EX001", "STX-S002"]


def test_ex001_message_explains_why_pragma_was_rejected():
    # Arrange
    src = "# stx-allow-file: STX-S002\n" + _NO_GUARD_BODY
    # Act
    issues = lint_source(src, filepath="bench_store.py", config=LinterConfig())
    ex = [i for i in issues if i.rule.id == "STX-EX001"]
    # Assert
    assert "reason" in ex[0].rule.message


def test_marker_inside_string_literal_is_ignored():
    # Arrange — only real comments / the module docstring count.
    src = 'X = "# stx-allow-file: STX-S002"\n'
    # Act
    scan = scan_file_exemptions(src)
    # Assert
    assert (scan.exemptions, scan.problems) == ([], [])


# --------------------------------------------------------------------------- #
# Audit output — exemptions are listed, never silent                          #
# --------------------------------------------------------------------------- #


def _write_exempted(tmp_path):
    f = tmp_path / "bench_store.py"
    f.write_text(
        "# stx-allow-file: STX-S002  (reason: measures the store)\n" + _NO_GUARD_BODY
    )
    return f


def test_validate_files_text_output_lists_exemption(tmp_path, capsys):
    # Arrange
    f = _write_exempted(tmp_path)
    # Act
    _do_check(str(tmp_path), False, True, "info", None)
    out = capsys.readouterr().out
    # Assert
    assert f"{f}:1  STX-S002  reason: measures the store" in out


def test_validate_files_json_meta_lists_exemption(tmp_path, capsys):
    # Arrange
    f = _write_exempted(tmp_path)
    # Act
    _do_check(str(tmp_path), True, True, "info", None)
    meta = json.loads(capsys.readouterr().out)["_meta"]
    # Assert
    assert meta["exemptions"] == [
        {
            "file": str(f),
            "rules": ["STX-S002"],
            "reason": "measures the store",
            "line": 1,
        }
    ]
