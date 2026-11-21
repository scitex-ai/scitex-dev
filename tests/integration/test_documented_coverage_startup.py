"""The specific trusted coverage-skill binding must work as a real .pth file."""

import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import coverage

from scitex_dev._ecosystem._skills.skills_verify import _python_blocks


def _documented_shim():
    root = Path(__file__).resolve().parents[2]
    skill = (
        root / "src/scitex_dev/_skills/general/05_development/06_subprocess-coverage.md"
    )
    values = []
    for _, code in _python_blocks(skill.read_text()):
        for node in ast.walk(ast.parse(code)):
            if (
                not isinstance(node, ast.FunctionDef)
                or node.name != "_ensure_subprocess_coverage_shim"
            ):
                continue
            for assignment in ast.walk(node):
                if isinstance(assignment, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "shim"
                    for target in assignment.targets
                ):
                    values.append(ast.literal_eval(assignment.value))
    if len(values) != 1 or not isinstance(values[0], str):
        raise AssertionError(
            "Expected exactly one literal binding in the trusted skill"
        )
    return values[0]


def _exercise_shim(root, shim):
    site = root / "owned-site"
    site.mkdir()
    (site / "documented.pth").write_text(shim)
    source = root / "owned-source"
    source.mkdir()
    probe = source / "probe.py"
    probe.write_text("only_in_child = 1\n")
    config = root / "coverage.ini"
    config.write_text(f"[run]\nparallel = true\nsource = {source}\n")
    environment = dict(
        os.environ,
        COVERAGE_PROCESS_START=str(config),
        COVERAGE_FILE=str(root / ".coverage"),
    )
    environment.pop("COVERAGE_PROCESS_CONFIG", None)
    # -S disables all installed startup bindings. Adding only the owned site
    # ensures coverage's own newer .pth cannot hide a broken documented shim.
    script = (
        "import sys,site,runpy,json; sys.path.insert(0,sys.argv[1]); "
        "site.addsitedir(sys.argv[2]); import coverage; "
        "runpy.run_path(sys.argv[3]); "
        "print(json.dumps({'active':coverage.Coverage.current() is not None}))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            script,
            str(Path(coverage.__file__).resolve().parent.parent),
            str(site),
            str(probe),
        ],
        env=environment,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    shards = list(root.glob(".coverage.*"))
    measured = []
    for shard in shards:
        data = coverage.CoverageData(basename=str(shard))
        data.read()
        measured.append(data.lines(str(probe)))
    return result, shards, measured


def test_documented_binding_starts_coverage_and_records_child_lines(tmp_path):
    # Arrange
    shim = _documented_shim()
    # Act
    result, shards, measured = _exercise_shim(tmp_path, shim)
    # Assert
    assert (
        result.returncode,
        json.loads(result.stdout),
        result.stderr,
        len(shards),
        measured,
    ) == (0, {"active": True}, "", 1, [[1]])
