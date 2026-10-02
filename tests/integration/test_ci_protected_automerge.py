"""Execute the actual sweep with synthetic gh responses and real jq."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
import jq

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/auto-merge-to-develop.yaml"


@pytest.fixture
def merge_case(tmp_path):
    binary = tmp_path / "gh"
    binary.write_text("#!" + sys.executable + "\n" + "import sys\n"
                      + "sys.path.insert(0," + repr(str(Path(jq.__file__).parent)) + ")\n"
                      + """import json,os
from pathlib import Path
import jq
args=sys.argv[1:]
if args[:2]==['pr','merge']:
    Path(os.environ['RECORD']).write_text('\\n'.join(args)+'\\n')
    raise SystemExit(int(os.environ.get('MERGE_EXIT','0')))
if args[:2]==['pr','list']:
    sys.stdout.write('1\\n')
    raise SystemExit(0)
query=args[args.index('--jq')+1]
response=json.loads(Path(os.environ['RESPONSE']).read_text())
for result in jq.compile(query).input_value(response).all():
    sys.stdout.write((result if isinstance(result,str) else json.dumps(result))+'\\n')
""")
    binary.chmod(0o700)
    response = tmp_path / "response.json"
    record = tmp_path / "merge-argv.txt"
    return binary, response, record


def execute(case, *, checks, draft=False, merge_exit="0"):
    binary, response, record = case
    response.write_text(json.dumps({"number": 1, "baseRefName": "develop",
                                   "isDraft": draft, "statusCheckRollup": checks}))
    workflow = yaml.safe_load(WORKFLOW.read_text())
    script = workflow["jobs"]["automerge"]["steps"][0]["run"]
    return subprocess.run(
        ["bash", "-c", script], cwd=ROOT, capture_output=True, text=True,
        env={"PATH": str(binary.parent) + ":/usr/bin:/bin", "REPO": "owned/fixture",
             "HEAD_SHA": "", "RESPONSE": str(response), "RECORD": str(record),
             "MERGE_EXIT": merge_exit},
    )


@pytest.mark.parametrize("check", [
    {"name": "pytest", "status": "QUEUED", "conclusion": ""},
    {"name": "pytest", "status": "IN_PROGRESS", "conclusion": None},
    {"name": "pytest", "conclusion": "FAILURE"},
    {"context": "audit", "state": "PENDING"},
])
def test_unfinished_or_failed_check_never_invokes_merge(merge_case, check):
    # Arrange
    case = merge_case
    # Act
    execute(case, checks=[check])
    # Assert
    assert not case[2].exists()


def test_draft_never_invokes_merge_even_with_green_checks(merge_case):
    # Arrange
    case = merge_case
    # Act
    execute(case, checks=[{"name": "pytest", "conclusion": "SUCCESS"}], draft=True)
    # Assert
    assert not case[2].exists()


def test_green_sweep_invokes_only_normal_protected_merge(merge_case):
    # Arrange
    case = merge_case
    # Act
    execute(case, checks=[{"name": "pytest", "conclusion": "SUCCESS"}])
    argv = case[2].read_text().splitlines()
    # Assert
    assert argv == ["pr", "merge", "1", "--repo", "owned/fixture", "--merge", "--delete-branch"]


def test_branch_policy_refusal_remains_blocked(merge_case):
    # Arrange
    case = merge_case
    # Act
    result = execute(case, checks=[{"name": "pytest", "conclusion": "SUCCESS"}], merge_exit="1")
    # Assert
    assert "blocked #1" in result.stdout and "MERGED #1" not in result.stdout
