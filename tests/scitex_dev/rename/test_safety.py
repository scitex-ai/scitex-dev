"""Real absent-ripgrep child environments retain Git and rename safeguards."""

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest


def _missing_rg_state(files):
    return [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns, stat.S_IMODE(f.stat().st_mode)) for f in files]


def _missing_rg_call(operation, root, bin_dir, regex):
    code = """
import dataclasses,json,shutil,sys
from scitex_dev import preview_rename,execute_rename
from scitex_dev.rename.config import RenameConfig
from scitex_dev.rename.filters import _RG_PATH,find_matching_files
from scitex_dev.rename.safety import is_git_repo,has_uncommitted_changes,check_directory_safety
operation,root,regex=sys.argv[1:];regex=regex=='True'
pattern=r'(?<=prefix:)needle' if regex else 'needle'
data={'rg':_RG_PATH,'which_rg':shutil.which('rg'),'git':shutil.which('git')}
if operation=='probe':
    data.update(repo=is_git_repo(root),dirty=has_uncommitted_changes(root),safety=check_directory_safety(root),files=list(map(str,find_matching_files(root,RenameConfig(pattern,'REPLACED',regex=regex),need_content_match=True))))
else:
    fn=preview_rename if operation=='preview' else execute_rename
    options={'directory':root,'regex':regex}
    if operation=='apply':options['skip_ids']=['c-001']
    data['result']=dataclasses.asdict(fn(pattern,'REPLACED',**options))
print(json.dumps(data))
"""
    result = subprocess.run([sys.executable, "-c", code, operation, str(root), str(regex)], env={**os.environ, "PATH": str(bin_dir)}, check=True, capture_output=True, timeout=15)
    return json.loads(result.stdout)


@pytest.fixture(params=[(regex, state) for regex in [False, True] for state in ["clean", "dirty", "nonrepo", "readonly"]])
def missing_rg_safety_case(request, tmp_path):
    regex, state = request.param
    git = shutil.which("git")
    assert git is not None, "Live rename safety requires actual Git"
    bin_dir = tmp_path / "tools"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(Path(git).resolve())
    root = tmp_path / "owned-repo"
    root.mkdir()
    for name in ["z.txt", "a.txt", "m.txt"]:
        (root / name).write_bytes(b"prefix:needle\n")
    files = [root / name for name in ["a.txt", "m.txt", "z.txt"]]
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unrelated\n")
    if state != "nonrepo":
        for args in [["init"], ["config", "user.name", "Owned absent rg fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned absent rg fixture"]]:
            subprocess.run([git, "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    if state == "dirty":
        files[0].write_bytes(b"prefix:needle\ndirty\n")
    if state == "readonly":
        descriptor = os.open(files[0], os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(descriptor)
            assert info.st_uid == os.getuid() and info.st_nlink == 1 and stat.S_ISREG(info.st_mode)
            os.fchmod(descriptor, 0o444)
        finally:
            os.close(descriptor)
    before = _missing_rg_state([*files, outside])
    yield root, bin_dir, files, outside, regex, state, before


def test_missing_rg_safety_actual_tools_and_discovery(missing_rg_safety_case):
    # Arrange
    root, bin_dir, files, _, regex, state, _ = missing_rg_safety_case
    # Act
    result = _missing_rg_call("probe", root, bin_dir, regex)
    # Assert
    assert (result["rg"], result["which_rg"], result["git"], result["repo"], result["dirty"], result["safety"] is None, result["files"]) == (None, None, str(bin_dir / "git"), state != "nonrepo", state == "dirty", state != "nonrepo", list(map(str, files)))


def test_missing_rg_safety_preview_ids(missing_rg_safety_case):
    # Arrange
    root, bin_dir, files, _, regex, _, _ = missing_rg_safety_case
    # Act
    result = _missing_rg_call("preview", root, bin_dir, regex)["result"]
    # Assert
    assert (result["summary"]["content_matches"], [(entry["id"], entry["file"]) for entry in result["contents"]]) == (3, [("c-000", str(files[0])), ("c-001", str(files[1])), ("c-002", str(files[2]))])


def test_missing_rg_safety_preview_preserves_fixture(missing_rg_safety_case):
    # Arrange
    root, bin_dir, files, outside, regex, _, before = missing_rg_safety_case
    # Act
    _missing_rg_call("preview", root, bin_dir, regex)
    after = _missing_rg_state([*files, outside])
    # Assert
    assert after == before


def test_missing_rg_safety_application_and_refusals(missing_rg_safety_case):
    # Arrange
    root, bin_dir, files, outside, regex, state, before = missing_rg_safety_case
    # Act
    result = _missing_rg_call("apply", root, bin_dir, regex)["result"]
    after = _missing_rg_state([*files, outside])
    error = result["error"]
    valid = error is None if state == "clean" else {"dirty": "uncommitted", "nonrepo": "git", "readonly": "permission"}[state] in (error or "").lower()
    observed = ([f.read_bytes() for f in files], after[1], after[-1]) if state == "clean" else after
    expected = ([b"prefix:REPLACED\n", b"prefix:needle\n", b"prefix:REPLACED\n"], before[1], before[-1]) if state == "clean" else before
    # Assert
    assert (valid, observed) == (True, expected)


_FALLBACK_LATE_NUL = b"needle\n" + b"x" * 65536 + b"\0\n"
_FALLBACK_CONTENT_INPUTS = [(b"\0needle\n", b"\0needle\n", 0), (b"needle\0tail\n", b"needle\0tail\n", 0), (_FALLBACK_LATE_NUL, _FALLBACK_LATE_NUL, 0), (b"needle\n", b"CHANGED\n", 1)]


def _fallback_content_call(operation, root, bin_dir, regex, pattern):
    code = """
import dataclasses,json,shutil,sys
from scitex_dev import preview_rename,execute_rename
from scitex_dev.rename.config import RenameConfig
from scitex_dev.rename.filters import _RG_PATH,find_matching_files
operation,root,options=sys.argv[1:];options=json.loads(options)
data={'rg':_RG_PATH,'which_rg':shutil.which('rg'),'git':shutil.which('git')}
if operation=='discovery':
    data['result']=list(map(str,find_matching_files(root,RenameConfig(options['pattern'],'CHANGED',regex=options['regex']),need_content_match=True)))
else:
    fn=preview_rename if operation=='preview' else execute_rename
    data['result']=dataclasses.asdict(fn(options['pattern'],'CHANGED',directory=root,regex=options['regex']))
print(json.dumps(data))
"""
    options = json.dumps({"regex": regex, "pattern": pattern})
    result = subprocess.run([sys.executable, "-c", code, operation, str(root), options], env={**os.environ, "PATH": str(bin_dir)}, check=True, capture_output=True, timeout=15)
    return json.loads(result.stdout)


@pytest.fixture(params=[(regex, body, "needle", expected, matches) for regex in [False, True] for body, expected, matches in _FALLBACK_CONTENT_INPUTS] + [(True, b"", "^$", b"CHANGED", 1), (False, b"", "needle", b"", 0), (False, b"\0needle\n", "\0", b"\0needle\n", 0), (True, b"\0needle\n", r"\x00", b"\0needle\n", 0), (True, b"\0needle\n", "\0", b"\0needle\n", 0), (True, b"needle\n", "needle|\0", b"CHANGED\n", 1)])
def fallback_content_case(request, tmp_path):
    regex, body, pattern, expected, matches = request.param
    git = shutil.which("git")
    assert git is not None, "Actual Git remains required for live rename safety"
    bin_dir = tmp_path / "tools"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(Path(git).resolve())
    root = tmp_path / "owned-repo"
    root.mkdir()
    file = root / "owned.txt"
    file.write_bytes(body)
    sibling = root / "other.txt"
    sibling.write_bytes(b"unrelated\n")
    (root / "archive").mkdir()
    archive = root / "archive" / "excluded.txt"
    archive.write_bytes(body)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(body)
    for args in [["init"], ["config", "user.name", "Owned fallback content fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned fallback content fixture"]]:
        subprocess.run([git, "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    protected = [sibling, archive, outside]
    before = _missing_rg_state([file, *protected])
    yield root, bin_dir, file, protected, regex, pattern, expected, matches, before


def test_fallback_content_actual_absent_rg_discovery(fallback_content_case):
    # Arrange
    root, bin_dir, file, _, regex, pattern, _, matches, _ = fallback_content_case
    # Act
    payload = _fallback_content_call("discovery", root, bin_dir, regex, pattern)
    # Assert
    assert (payload["rg"], payload["which_rg"], payload["git"], payload["result"]) == (None, None, str(bin_dir / "git"), [str(file)] if matches else [])


def test_fallback_content_preview_preserves_all_metadata(fallback_content_case):
    # Arrange
    root, bin_dir, file, protected, regex, pattern, _, matches, before = fallback_content_case
    # Act
    payload = _fallback_content_call("preview", root, bin_dir, regex, pattern)
    result = payload["result"]
    after = _missing_rg_state([file, *protected])
    # Assert
    assert (payload["rg"], payload["which_rg"], payload["git"], result["summary"]["content_matches"], bool(result["contents"]), after) == (None, None, str(bin_dir / "git"), matches, bool(matches), before)


def test_fallback_content_application_bytes_and_exclusions(fallback_content_case):
    # Arrange
    root, bin_dir, file, protected, regex, pattern, expected, matches, before = fallback_content_case
    # Act
    payload = _fallback_content_call("apply", root, bin_dir, regex, pattern)
    result = payload["result"]
    after = _missing_rg_state([file, *protected])
    # Assert
    assert (payload["rg"], payload["which_rg"], payload["git"], result["error"], result["summary"]["content_matches"], after[0][0], after[1:], after == before) == (None, None, str(bin_dir / "git"), None, matches, expected, before[1:], expected == before[0][0])


def _symlink_noop_state(link):
    info = link.lstat()
    return os.readlink(link), info.st_ino, info.st_mtime_ns, stat.S_IMODE(info.st_mode)


@pytest.fixture(params=[(regex, target_kind, changed) for regex in [False, True] for target_kind in ["file", "directory", "dangling"] for changed in [False, True]])
def symlink_noop_case(request, tmp_path):
    regex, target_kind, changed = request.param
    root = tmp_path / "owned-repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = []
    for name in ["needle", "CHANGED"]:
        target = outside / name
        if target_kind == "directory":
            target.mkdir()
            target = target / "sentinel.txt"
        if target_kind != "dangling":
            target.write_bytes(b"unrelated outside content\n")
            protected.append(target)
    sibling = root / "other.txt"
    sibling.write_bytes(b"unrelated sibling\n")
    protected.append(sibling)
    link = root / "owned-link"
    old_target = "../outside/needle"
    new_target = "../outside/CHANGED" if changed else old_target
    link.symlink_to(old_target)
    os.utime(link, ns=(1600000000000000000, 1600000000000000000), follow_symlinks=False)
    for args in [["init"], ["config", "user.name", "Owned symlink no-op fixture"], ["config", "user.email", "owned@example.invalid"], ["add", "."], ["commit", "-m", "owned symlink no-op fixture"]]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=10)
    pattern = "(needle)" if regex else "needle"
    replacement = "CHANGED" if changed else (r"\1" if regex else "needle")
    record = {"id": "st-000", "link": str(link), "old_target": old_target, "new_target": new_target}
    before = (_symlink_noop_state(link), _missing_rg_state(protected))
    yield root, link, protected, regex, pattern, replacement, changed, record, before


def test_symlink_noop_preview_reports_selected_targets(symlink_noop_case):
    # Arrange
    from scitex_dev import preview_rename
    root, _, _, regex, pattern, replacement, _, record, _ = symlink_noop_case
    # Act
    result = preview_rename(pattern, replacement, directory=str(root), regex=regex)
    # Assert
    assert (result.summary["symlink_targets_updated"], result.symlink_targets) == (1, [record])


def test_symlink_noop_preview_preserves_link_and_targets(symlink_noop_case):
    # Arrange
    from scitex_dev import preview_rename
    root, link, protected, regex, pattern, replacement, _, _, before = symlink_noop_case
    # Act
    preview_rename(pattern, replacement, directory=str(root), regex=regex)
    after = (_symlink_noop_state(link), _missing_rg_state(protected))
    # Assert
    assert after == before


def test_symlink_noop_application_preserves_unchanged_link(symlink_noop_case):
    # Arrange
    from scitex_dev import execute_rename
    root, link, protected, regex, pattern, replacement, changed, record, before = symlink_noop_case
    # Act
    result = execute_rename(pattern, replacement, directory=str(root), regex=regex)
    after = (_symlink_noop_state(link), _missing_rg_state(protected))
    # Assert
    assert (result.error, result.summary["symlink_targets_updated"], result.symlink_targets, after[0][0], after[1], after[0] == before[0]) == (None, 1, [record], record["new_target"], before[1], not changed)
