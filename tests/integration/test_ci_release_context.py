"""Execute release isolation with real imports and owned refusal controls."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ROOT / ".github/ci/release-context.sh"


@pytest.fixture
def release_case(tmp_path):
    scratch = tmp_path / "job scratch with spaces"
    scratch.mkdir()
    private = tmp_path / "private-home"
    private.mkdir()
    probe = tmp_path / "probe.py"
    probe.write_text(
        """import json,os,sys
from pathlib import Path
private=Path(sys.argv[1]).resolve()
owned=private.parent
base=Path(sys.base_prefix).resolve()
def refuse(event,args):
    if event in {'socket.connect','socket.bind','socket.getaddrinfo'}:
        raise RuntimeError('release probe refuses sockets')
    if event in {'open','os.mkdir','os.listdir','os.scandir'} and args and isinstance(args[0],(str,bytes,os.PathLike)):
        path=Path(os.fsdecode(args[0])).resolve()
        mode=args[1] if event=='open' and len(args)>1 else None
        flags=args[2] if event=='open' and len(args)>2 else 0
        writing=event=='os.mkdir' or (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC))
        personal=path==private or private in path.parents or str(path).startswith(('/home/','/root/'))
        interpreter_read=not writing and (path==base or base in path.parents)
        if personal and not interpreter_read:
            raise RuntimeError('release probe refuses personal state')
        if writing and path!=Path('/dev/null') and path!=owned and owned not in path.parents:
            raise RuntimeError('release probe refuses writes outside owned scratch')
sys.addaudithook(refuse)
state_names=['TMPDIR','SCITEX_DIR','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_RUNTIME_DIR','UV_CACHE_DIR','PIP_CACHE_DIR','PGHOST']
report={'paths':{name:os.environ.get(name) for name in state_names},
        'ambient_present':any(name in os.environ for name in ['OWNED_PROVIDER_FIXTURE','DATABASE_URL','PYTHONPATH','VIRTUAL_ENV','HOME']),
        'port':os.environ.get('PGPORT')}
if sys.argv[2]=='import':
    sys.path.insert(0,sys.argv[3])
    import scitex_logging
    from scitex_dev._cli import main
    from scitex_dev.store import host_store
    from urllib.parse import parse_qs,urlparse
    dsn=host_store(pkg='qualification',name='release').dsn
    report['store_refused']=parse_qs(urlparse(dsn).query).get('host')==[os.environ['PGHOST']]
    report['entrypoint_callable']=callable(main)
    state=Path(os.environ['SCITEX_DIR']).resolve()
    report['daily_log_owned']=any(state.rglob('scitex-*.log'))
sys.stdout.write(json.dumps(report)+'\\n')
"""
    )
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(private),
        "OWNED_PROVIDER_FIXTURE": "owned-synthetic-fixture",
        "DATABASE_URL": "owned-synthetic-fixture",
        "VIRTUAL_ENV": str(private / "unused-venv"),
        "PYTHONPATH": str(private / "unused-imports"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return scratch, private, probe, environment


def execute(case, mode="environment", context=CONTEXT):
    scratch, private, probe, environment = case
    command = """set -euo pipefail
source "$1"
scitex_release_context "$2" "$3"
scitex_release_run "$4" "$5" "$6" "$7" "$8"
"""
    return subprocess.run(
        ["bash", "-c", command, "release-probe", str(context), str(scratch),
         str(Path(sys.executable).parent.parent), sys.executable, str(probe),
         str(private), mode, str(ROOT / "src")],
        env=environment, cwd=ROOT, capture_output=True, text=True,
    )


def test_real_entrypoint_import_and_daily_log_use_owned_state(release_case):
    # Arrange
    case = release_case
    # Act
    result = execute(case, mode="import")
    report = json.loads(result.stdout) if result.returncode == 0 else {}
    # Assert
    assert (result.returncode, report.get("entrypoint_callable"),
            report.get("daily_log_owned"), report.get("store_refused")) == (0, True, True, True), result.stderr


def test_ambient_provider_and_user_overrides_do_not_reach_child(release_case):
    # Arrange
    case = release_case
    # Act
    result = execute(case)
    report = json.loads(result.stdout)
    # Assert
    assert report["ambient_present"] is False


def test_all_state_and_cache_paths_belong_to_job_scratch(release_case):
    # Arrange
    case = release_case
    scratch = case[0]
    # Act
    result = execute(case)
    paths = json.loads(result.stdout)["paths"]
    # Assert
    assert all(Path(value) == scratch or scratch in Path(value).parents for value in paths.values())


def test_store_refusal_uses_nonexistent_owned_socket_and_port_one(release_case):
    # Arrange
    case = release_case
    # Act
    result = execute(case)
    report = json.loads(result.stdout)
    # Assert
    assert (Path(report["paths"]["PGHOST"]).exists(), report["port"]) == (False, "1")


def test_existing_refusal_socket_path_aborts_before_child(release_case):
    # Arrange
    case = release_case
    (case[0] / "refused-store-socket").mkdir()
    # Act
    result = execute(case)
    # Assert
    assert result.returncode != 0 and not result.stdout


def test_missing_release_scratch_aborts_before_child(release_case):
    # Arrange
    scratch, private, probe, environment = release_case
    case = scratch / "absent", private, probe, environment
    # Act
    result = execute(case)
    # Assert
    assert result.returncode != 0 and not result.stdout


def test_unisolated_real_logger_import_reaches_private_home_refusal(release_case):
    # Arrange
    _, private, probe, environment = release_case
    # Act
    result = subprocess.run(
        [sys.executable, str(probe), str(private), "import", str(ROOT / "src")],
        env=environment, cwd=ROOT, capture_output=True, text=True,
    )
    # Assert
    assert result.returncode != 0 and "release probe refuses personal state" in result.stderr


def test_unisolated_environment_exposes_synthetic_provider_control(release_case):
    # Arrange
    _, private, probe, environment = release_case
    # Act
    result = subprocess.run(
        [sys.executable, str(probe), str(private), "environment"],
        env=environment, cwd=ROOT, capture_output=True, text=True,
    )
    # Assert
    assert json.loads(result.stdout)["ambient_present"] is True


def test_actual_mint_failure_block_reports_only_error_codes(release_case):
    # Arrange
    scratch, _, _, environment = release_case
    publisher = (ROOT / ".github/ci/publish-in-sif.sh").read_text()
    block = publisher.split('if [ -z "$MINTED" ]; then', 1)[1].split('\nfi', 1)[0]
    response = scratch / "mint-response.json"
    response.write_text(json.dumps({"errors": [{"code": "invalid-publisher",
                                               "description": "owned-response-field-not-for-log"}],
                                    "credential": "owned-response-field-not-for-log"}))
    command = """set -euo pipefail
source "$1"
scitex_release_context "$2" "$3"
PY="$4"
MINT_RESP=$(cat "$5")
""" + block
    # Act
    result = subprocess.run(
        ["bash", "-c", command, "mint-failure", str(CONTEXT), str(scratch),
         str(Path(sys.executable).parent.parent), sys.executable, str(response)],
        env=environment, cwd=ROOT, capture_output=True, text=True,
    )
    # Assert
    assert (result.returncode, "invalid-publisher" in result.stdout,
            "owned-response-field-not-for-log" in result.stdout) == (1, True, False)
