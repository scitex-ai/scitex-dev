"""Real ripgrep pattern binding preserves option-shaped search strings."""

import shutil
import subprocess

import pytest

from scitex_dev import execute_rename, preview_rename
from scitex_dev.rename.config import RenameConfig
from scitex_dev.rename.filters import _RG_PATH, _rg_find_content_matches

pytestmark = pytest.mark.skipif(shutil.which("rg") is None, reason="Optional ripgrep backend is not installed")


@pytest.fixture(params=[(regex, pattern) for regex in [False, True] for pattern in ["--version", "--help", "needle"]])
def rg_option_case(request, tmp_path):
    regex, pattern = request.param
    assert _RG_PATH is not None, "This cohort requires an actual installed ripgrep backend"
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / "owned.txt"
    file.write_text(pattern + "\n")
    (root / "other.txt").write_text("unrelated\n")
    for args in [["init"], ["config", "user.name", "Owned rg fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned rg fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    info = file.stat()
    return root, file, regex, pattern, (file.read_bytes(), info.st_ino, info.st_mtime_ns)


def test_rg_option_backend_finds_exact_real_file(rg_option_case):
    # Arrange
    root, file, regex, pattern, _ = rg_option_case
    config = RenameConfig(pattern, "REPLACED", regex=regex)
    # Act
    files = _rg_find_content_matches(str(root), config)
    # Assert
    assert files == [file]


def test_rg_option_public_preview_counts_content_match(rg_option_case):
    # Arrange
    root, _, regex, pattern, _ = rg_option_case
    # Act
    result = preview_rename(pattern, "REPLACED", directory=str(root), regex=regex)
    # Assert
    assert result.summary["content_matches"] == 1


def test_rg_option_preview_preserves_file_metadata(rg_option_case):
    # Arrange
    root, file, regex, pattern, before = rg_option_case
    # Act
    preview_rename(pattern, "REPLACED", directory=str(root), regex=regex)
    info = file.stat()
    # Assert
    assert (file.read_bytes(), info.st_ino, info.st_mtime_ns) == before


def test_rg_option_actual_apply_replaces_only_expected_content(rg_option_case):
    # Arrange
    root, file, regex, pattern, _ = rg_option_case
    # Act
    result = execute_rename(pattern, "REPLACED", directory=str(root), regex=regex)
    # Assert
    assert (result.error, file.read_text(), (root / "other.txt").read_text()) == (None, "REPLACED\n", "unrelated\n")


@pytest.fixture(params=["ordinary.txt", "line\nbreak.txt", "carriage\rreturn.txt", "tab\tbreak.txt", "unicode\u2028break.txt", "sibling-spoof"])
def rg_filename_case(request, tmp_path):
    assert _RG_PATH is not None, "This cohort requires an actual installed ripgrep backend"
    root = tmp_path / "owned-repo"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("needle external sentinel\n")
    name = request.param
    if name == "sibling-spoof":
        name = "prefix\n" + str(outside)
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("needle\n")
    for args in [["init"], ["config", "user.name", "Owned filename fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned filename fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, outside)]
    return root, file, outside, before


def test_rg_filename_backend_selects_exact_path(rg_filename_case):
    # Arrange
    root, file, _, _ = rg_filename_case
    config = RenameConfig("needle", "REPLACED")
    # Act
    files = _rg_find_content_matches(str(root), config)
    # Assert
    assert files == [file]


def test_rg_filename_public_preview_selects_exact_path(rg_filename_case):
    # Arrange
    root, file, _, _ = rg_filename_case
    # Act
    result = preview_rename("needle", "REPLACED", directory=str(root))
    # Assert
    assert (result.summary["content_matches"], [entry["file"] for entry in result.contents]) == (1, [str(file)])


def test_rg_filename_preview_preserves_both_files(rg_filename_case):
    # Arrange
    root, file, outside, before = rg_filename_case
    # Act
    preview_rename("needle", "REPLACED", directory=str(root))
    after = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, outside)]
    # Assert
    assert after == before


def test_rg_filename_application_preserves_sibling(rg_filename_case):
    # Arrange
    root, file, outside, _ = rg_filename_case
    # Act
    result = execute_rename("needle", "REPLACED", directory=str(root))
    # Assert
    assert (result.error, file.read_text(), outside.read_text()) == (None, "REPLACED\n", "needle external sentinel\n")


@pytest.fixture(params=[b"ordinary.txt", b"invalid-\xff.txt", b"invalid-\xfe.txt", b"invalid-\xff\nline.txt"])
def rg_byte_name_case(request, tmp_path):
    import os

    assert _RG_PATH is not None, "This cohort requires an actual installed ripgrep backend"
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / os.fsdecode(request.param)
    file.write_text("needle\n")
    sibling = root / "other.txt"
    sibling.write_text("unrelated\n")
    for args in [["init"], ["config", "user.name", "Owned byte filename fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned byte filename fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, sibling)]
    return root, file, sibling, before


def test_rg_byte_name_backend_exact_path(rg_byte_name_case):
    # Arrange
    root, file, _, _ = rg_byte_name_case
    config = RenameConfig("needle", "REPLACED")
    # Act
    result = _rg_find_content_matches(str(root), config)
    # Assert
    assert result == [file]


def test_rg_byte_name_preview_exact_path(rg_byte_name_case):
    # Arrange
    root, file, _, _ = rg_byte_name_case
    # Act
    result = preview_rename("needle", "REPLACED", directory=str(root))
    # Assert
    assert (result.summary["content_matches"], [entry["file"] for entry in result.contents]) == (1, [str(file)])


def test_rg_byte_name_preview_preserves_metadata(rg_byte_name_case):
    # Arrange
    root, file, sibling, before = rg_byte_name_case
    # Act
    preview_rename("needle", "REPLACED", directory=str(root))
    after = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, sibling)]
    # Assert
    assert after == before


def test_rg_byte_name_apply_preserves_sibling(rg_byte_name_case):
    # Arrange
    root, file, sibling, _ = rg_byte_name_case
    # Act
    result = execute_rename("needle", "REPLACED", directory=str(root))
    # Assert
    assert (result.error, file.read_bytes(), sibling.read_bytes()) == (None, b"REPLACED\n", b"unrelated\n")


def test_rg_byte_name_cli_preview_exact_json_path(rg_byte_name_case):
    # Arrange
    import json
    from click.testing import CliRunner
    from scitex_dev._cli._root import main

    root, file, _, _ = rg_byte_name_case
    # Act
    result = CliRunner().invoke(main, ["rename-symbols", "--root", str(root), "--dry-run", "--json", "needle", "REPLACED"])
    payload = json.loads(result.stdout)
    # Assert
    assert (result.exit_code, payload["success"] is True, [entry["file"] for entry in payload["data"]["contents"]]) == (0, True, [str(file)])


def test_rg_byte_name_cli_apply_preserves_sibling(rg_byte_name_case):
    # Arrange
    import json
    from click.testing import CliRunner
    from scitex_dev._cli._root import main

    root, file, sibling, _ = rg_byte_name_case
    # Act
    result = CliRunner().invoke(main, ["rename-symbols", "--root", str(root), "--yes", "--json", "needle", "REPLACED"])
    payload = json.loads(result.stdout)
    # Assert
    assert (result.exit_code, payload["success"] is True, [entry["file"] for entry in payload["data"]["contents"]], file.read_bytes(), sibling.read_bytes()) == (0, True, [str(file)], b"REPLACED\n", b"unrelated\n")


def _run_owned_rg_config(operation, root, config_file, regex):
    import json
    import os
    import sys

    code = """
import dataclasses,json,sys
from scitex_dev import preview_rename,execute_rename
from scitex_dev.rename.config import RenameConfig
from scitex_dev.rename.filters import _rg_find_content_matches
operation,root,regex=sys.argv[1:];regex=regex=='True'
if operation=='backend':
    files=_rg_find_content_matches(root,RenameConfig('needle','REPLACED',regex=regex))
    data=None if files is None else list(map(str,files))
else:
    fn=preview_rename if operation=='preview' else execute_rename
    data=dataclasses.asdict(fn('needle','REPLACED',directory=root,regex=regex))
print(json.dumps(data))
"""
    result = subprocess.run([sys.executable, "-c", code, operation, str(root), str(regex)], env={**os.environ, "RIPGREP_CONFIG_PATH": str(config_file)}, check=True, capture_output=True, timeout=15)
    return json.loads(result.stdout)


@pytest.fixture(params=[(regex, options) for regex in [False, True] for options in ["", "--quiet\n", "--glob=!*.txt\n"]])
def rg_config_case(request, tmp_path):
    regex, options = request.param
    assert _RG_PATH is not None, "This cohort requires an actual installed ripgrep backend"
    config_file = tmp_path / "ripgrep.config"
    config_file.write_text(options)
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / "owned.txt"
    file.write_text("needle\n")
    sibling = root / "other.txt"
    sibling.write_text("unrelated\n")
    for args in [["init"], ["config", "user.name", "Owned rg config fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned rg config fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, sibling, config_file)]
    return root, file, sibling, config_file, regex, before


def test_rg_config_backend_exact_selection(rg_config_case):
    # Arrange
    root, file, _, config_file, regex, _ = rg_config_case
    # Act
    files = _run_owned_rg_config("backend", root, config_file, regex)
    # Assert
    assert files == [str(file)]


def test_rg_config_preview_exact_selection(rg_config_case):
    # Arrange
    root, file, _, config_file, regex, _ = rg_config_case
    # Act
    result = _run_owned_rg_config("preview", root, config_file, regex)
    # Assert
    assert (result["summary"]["content_matches"], [entry["file"] for entry in result["contents"]]) == (1, [str(file)])


def test_rg_config_preview_preserves_owned_files(rg_config_case):
    # Arrange
    root, file, sibling, config_file, regex, before = rg_config_case
    # Act
    _run_owned_rg_config("preview", root, config_file, regex)
    after = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, sibling, config_file)]
    # Assert
    assert after == before


def test_rg_config_apply_uses_rename_configuration(rg_config_case):
    # Arrange
    root, file, sibling, config_file, regex, before = rg_config_case
    # Act
    result = _run_owned_rg_config("apply", root, config_file, regex)
    preserved = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (sibling, config_file)]
    # Assert
    assert (result["error"], file.read_bytes(), preserved) == (None, b"REPLACED\n", before[1:])


@pytest.fixture(params=[["z.txt", "a.txt", "m.txt"], ["a.txt", "m.txt", "z.txt"], ["m.txt", "z.txt", "a.txt"]])
def fallback_order_case(request, tmp_path):
    assert _RG_PATH is not None, "This cohort requires an actual installed ripgrep backend"
    root = tmp_path / "owned-repo"
    root.mkdir()
    files = [root / name for name in request.param]
    for file in files:
        file.write_bytes(b"prefix:needle\n")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unrelated\n")
    for args in [["init"], ["config", "user.name", "Owned fallback order fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned fallback order fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in [*files, outside]]
    return root, files, outside, before


def test_fallback_order_real_regex_failure_signal(fallback_order_case):
    # Arrange
    root, _, _, _ = fallback_order_case
    config = RenameConfig(r"(?<=prefix:)needle", "REPLACED", regex=True)
    # Act
    files = _rg_find_content_matches(str(root), config)
    # Assert
    assert files is None


def test_fallback_order_plain_discovery_is_sorted(fallback_order_case):
    # Arrange
    from scitex_dev.rename.filters import find_matching_files

    root, _, _, _ = fallback_order_case
    config = RenameConfig(r"(?<=prefix:)needle", "REPLACED", regex=True)
    # Act
    files = find_matching_files(str(root), config)
    # Assert
    assert files == [root / "a.txt", root / "m.txt", root / "z.txt"]


def test_fallback_order_content_discovery_is_sorted(fallback_order_case):
    # Arrange
    from scitex_dev.rename.filters import find_matching_files

    root, _, _, _ = fallback_order_case
    config = RenameConfig(r"(?<=prefix:)needle", "REPLACED", regex=True)
    # Act
    files = find_matching_files(str(root), config, need_content_match=True)
    # Assert
    assert files == [root / "a.txt", root / "m.txt", root / "z.txt"]


def test_fallback_order_preview_assigns_sorted_ids(fallback_order_case):
    # Arrange
    root, _, _, _ = fallback_order_case
    # Act
    result = preview_rename(r"(?<=prefix:)needle", "REPLACED", directory=str(root), regex=True)
    # Assert
    assert [(entry["id"], entry["file"]) for entry in result.contents] == [("c-000", str(root / "a.txt")), ("c-001", str(root / "m.txt")), ("c-002", str(root / "z.txt"))]


def test_fallback_order_preview_preserves_fixture(fallback_order_case):
    # Arrange
    root, files, outside, before = fallback_order_case
    # Act
    preview_rename(r"(?<=prefix:)needle", "REPLACED", directory=str(root), regex=True)
    after = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in [*files, outside]]
    # Assert
    assert after == before


def test_fallback_order_apply_skip_keeps_first_sorted_file(fallback_order_case):
    # Arrange
    root, _, outside, before = fallback_order_case
    # Act
    result = execute_rename(r"(?<=prefix:)needle", "REPLACED", directory=str(root), regex=True, skip_ids=["c-000"])
    outside_after = (outside.read_bytes(), outside.stat().st_ino, outside.stat().st_mtime_ns)
    # Assert
    assert (result.error, (root / "a.txt").read_bytes(), (root / "m.txt").read_bytes(), (root / "z.txt").read_bytes(), outside_after) == (None, b"prefix:needle\n", b"prefix:REPLACED\n", b"prefix:REPLACED\n", before[-1])



def test_fallback_order_apply_skip_keeps_second_sorted_file(fallback_order_case):
    # Arrange
    root, _, outside, before = fallback_order_case
    # Act
    result = execute_rename(r"(?<=prefix:)needle", "REPLACED", directory=str(root), regex=True, skip_ids=["c-001"])
    outside_after = (outside.read_bytes(), outside.stat().st_ino, outside.stat().st_mtime_ns)
    # Assert
    assert (result.error, (root / "a.txt").read_bytes(), (root / "m.txt").read_bytes(), (root / "z.txt").read_bytes(), outside_after) == (None, b"prefix:REPLACED\n", b"prefix:needle\n", b"prefix:REPLACED\n", before[-1])


@pytest.fixture(params=[
    (r"needle\n", b"needle\r\n", b"REPLACED", "needle\n"),
    (r"needle$", b"needle\r\n", b"REPLACED\n", "needle"),
    (r"(?m)^needle$", b"head\r\nneedle\r\ntail\r\n", b"head\nREPLACED\ntail\n", "needle"),
    (r"head\nneedle\ntail\n", b"head\rneedle\rtail\r", b"REPLACED", "head\nneedle\ntail\n"),
    (r"needle\n", b"needle\n", b"REPLACED", "needle\n"),
    (r"needle", b"needle\r\n", b"REPLACED\n", "needle"),
    (r"(?<=head\n)needle", b"head\r\nneedle\r\n", b"head\nREPLACED\n", "needle"),
    (r"(?m)^needle$", b"head\nneedle\ntail\n", b"head\nREPLACED\ntail\n", "needle"),
])
def regex_text_case(request, tmp_path):
    pattern, body, expected, matched = request.param
    assert _RG_PATH is not None, "This regression cohort requires actual ripgrep availability"
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / "owned.txt"
    file.write_bytes(body)
    sibling = root / "other.txt"
    sibling.write_bytes(b"unrelated\n")
    for args in [["init"], ["config", "user.name", "Owned regex text fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned regex text fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, sibling)]
    return root, file, sibling, pattern, expected, matched, before


def test_regex_text_discovery_uses_application_text(regex_text_case):
    # Arrange
    from scitex_dev.rename.filters import find_matching_files

    root, file, _, pattern, _, _, _ = regex_text_case
    config = RenameConfig(pattern, "REPLACED", regex=True)
    # Act
    files = find_matching_files(str(root), config, need_content_match=True)
    # Assert
    assert files == [file]


def test_regex_text_preview_reports_normalized_match(regex_text_case):
    # Arrange
    root, file, _, pattern, _, matched, _ = regex_text_case
    # Act
    result = preview_rename(pattern, "REPLACED", directory=str(root), regex=True)
    # Assert
    assert (result.summary["content_matches"], [(entry["file"], [(line["before"], line["after"]) for line in entry["lines"]]) for entry in result.contents]) == (1, [(str(file), [(matched, "REPLACED")])])


def test_regex_text_preview_preserves_original_bytes(regex_text_case):
    # Arrange
    root, file, sibling, pattern, _, _, before = regex_text_case
    # Act
    preview_rename(pattern, "REPLACED", directory=str(root), regex=True)
    after = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in (file, sibling)]
    # Assert
    assert after == before


def test_regex_text_application_keeps_python_semantics(regex_text_case):
    # Arrange
    root, file, sibling, pattern, expected, _, before = regex_text_case
    # Act
    result = execute_rename(pattern, "REPLACED", directory=str(root), regex=True)
    sibling_after = (sibling.read_bytes(), sibling.stat().st_ino, sibling.stat().st_mtime_ns)
    # Assert
    assert (result.error, file.read_bytes(), sibling_after) == (None, expected, before[1])


_LATE_NUL = b"needle\n" + b"x" * 65536 + b"\0\n"
_NUL_INPUTS = [(b"\0needle\n", b"\0needle\n", 0), (b"needle\0tail\n", b"needle\0tail\n", 0), (_LATE_NUL, _LATE_NUL, 0), (b"needle\n", b"CHANGED\n", 1)]

@pytest.fixture(params=[(regex, body, "needle", expected, matches) for regex in [False, True] for body, expected, matches in _NUL_INPUTS] + [(True, b"", "^$", b"CHANGED", 1), (False, b"", "needle", b"", 0), (False, b"\0needle\n", "\0", b"\0needle\n", 0), (True, b"\0needle\n", r"\x00", b"\0needle\n", 0), (True, b"\0needle\n", "\0", b"\0needle\n", 0), (True, b"needle\n", "needle|\0", b"CHANGED\n", 1)])
def nul_content_case(request, tmp_path):
    assert _RG_PATH is not None, "This cohort checks actual ripgrep availability"
    regex, body, pattern, expected, matches = request.param
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / "owned.txt"
    file.write_bytes(body)
    for args in [["init"], ["config", "user.name", "Owned NUL content fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned NUL content fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    before = (file.read_bytes(), file.stat().st_ino, file.stat().st_mtime_ns)
    yield root, file, regex, pattern, expected, matches, before


def test_nul_content_discovery_excludes_nul_input(nul_content_case):
    # Arrange
    from scitex_dev.rename.filters import find_matching_files
    root, file, regex, pattern, _, matches, _ = nul_content_case
    config = RenameConfig(pattern, "CHANGED", regex=regex)
    # Act
    files = find_matching_files(str(root), config, need_content_match=True)
    # Assert
    assert files == ([file] if matches else [])


def test_nul_content_preview_preserves_input(nul_content_case):
    # Arrange
    root, file, regex, pattern, _, matches, before = nul_content_case
    # Act
    result = preview_rename(pattern, "CHANGED", directory=str(root), regex=regex)
    after = (file.read_bytes(), file.stat().st_ino, file.stat().st_mtime_ns)
    # Assert
    assert (result.summary["content_matches"], after) == (matches, before)


def test_nul_content_application_preserves_excluded_input(nul_content_case):
    # Arrange
    root, file, regex, pattern, expected, matches, before = nul_content_case
    # Act
    result = execute_rename(pattern, "CHANGED", directory=str(root), regex=regex)
    after = (file.read_bytes(), file.stat().st_ino, file.stat().st_mtime_ns)
    # Assert
    assert (result.error, result.summary["content_matches"], after[0], after == before) == (None, matches, expected, expected == before[0])
