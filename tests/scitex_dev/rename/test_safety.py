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
