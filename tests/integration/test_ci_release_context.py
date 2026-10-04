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
environment=Path(sys.prefix).resolve()
source=Path(sys.argv[3]).resolve() if len(sys.argv)>3 else None
def refuse(event,args):
    if event in {'socket.connect','socket.bind','socket.getaddrinfo'}:
        raise RuntimeError('release probe refuses sockets')
    if event in {'open','os.mkdir','os.listdir','os.scandir'} and args and isinstance(args[0],(str,bytes,os.PathLike)):
        path=Path(os.fsdecode(args[0])).resolve()
        mode=args[1] if event=='open' and len(args)>1 else None
        flags=args[2] if event=='open' and len(args)>2 else 0
        writing=event=='os.mkdir' or (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC))
        personal=path==private or private in path.parents or str(path).startswith(('/home/','/root/'))
        interpreter_read=not writing and any(path==root or root in path.parents for root in (base,environment))
        source_read=not writing and source is not None and (path==source or source in path.parents)
        if (path==private or private in path.parents) or (personal and not (interpreter_read or source_read)):
            raise RuntimeError('release probe refuses personal state')
        if writing and path!=Path('/dev/null') and path!=owned and owned not in path.parents:
            raise RuntimeError('release probe refuses writes outside owned scratch')
sys.addaudithook(refuse)
state_names=['TMPDIR','SCITEX_DIR','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_RUNTIME_DIR','UV_CACHE_DIR','PIP_CACHE_DIR','SCITEX_TESTMON_CACHE_ROOT','PGHOST']
report={'paths':{name:os.environ.get(name) for name in state_names},
        'ambient_present':any(name in os.environ for name in ['OWNED_PROVIDER_FIXTURE','DATABASE_URL','PYTHONPATH','VIRTUAL_ENV','HOME']),
        'ambient_without_loader':any(name in os.environ for name in ['OWNED_PROVIDER_FIXTURE','DATABASE_URL','VIRTUAL_ENV','HOME']),
        'loader_paths':os.environ.get('PYTHONPATH','').split(os.pathsep),
        'port':os.environ.get('PGPORT')}
if sys.argv[2]=='source_read':
    report['source_read']=bool((source/'scitex_dev/__init__.py').read_bytes())
if sys.argv[2]=='private_read':
    list(private.iterdir())
if sys.argv[2]=='source_write':
    (source/'qualification-refused-write').write_text('must-never-be-written')
if sys.argv[2] in {'import','audit','source'}:
    sys.path.insert(0,sys.argv[3])
    import scitex_logging
    from scitex_dev._cli import main
    from scitex_dev.store import host_store
    from urllib.parse import parse_qs,urlparse
    dsn=host_store(pkg='qualification',name='release').dsn
    report['store_refused']=parse_qs(urlparse(dsn).query).get('host')==[os.environ['PGHOST']]
    from urllib.parse import unquote
    report['store_owned_socket']=unquote(urlparse(dsn).hostname or '')==os.environ.get('PGHOST')
    report['entrypoint_callable']=callable(main)
    state=Path(os.environ['SCITEX_DIR']).resolve()
    report['daily_log_owned']=any(state.rglob('scitex-*.log'))
if sys.argv[2]=='audit':
    import contextlib,io
    from scitex_dev._cli.audit._project._audit import audit_project
    from scitex_dev._cli.ecosystem._cmds._audit_masking import classify_output
    project=owned/'synthetic-project'
    project.mkdir()
    (project/'pyproject.toml').write_text('[project]\\nname="scitex-release-fixture"\\nversion="0.0.0"\\n')
    config=project/'.scitex/dev/config.yaml'
    config.parent.mkdir(parents=True)
    config.write_text('project-type: [pip, deferred]\\n')
    (project/'owned_extra').mkdir()
    stream=io.StringIO()
    with contextlib.redirect_stderr(stream):
        code=audit_project('scitex-release-fixture',repo=project,rules={'PS-103'})
    classified=classify_output(stream.getvalue(),())
    report['audit_result']=[code,classified.is_answerable(),classified.unmasked_count]
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
        env=environment, cwd=ROOT, capture_output=True, text=True, check=False,
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
        env=environment, cwd=ROOT, capture_output=True, text=True, check=False,
    )
    # Assert
    assert result.returncode != 0 and "release probe refuses personal state" in result.stderr


def test_unisolated_environment_exposes_synthetic_provider_control(release_case):
    # Arrange
    _, private, probe, environment = release_case
    # Act
    result = subprocess.run(
        [sys.executable, str(probe), str(private), "environment"],
        env=environment, cwd=ROOT, capture_output=True, text=True, check=False,
    )
    # Assert
    assert json.loads(result.stdout)["ambient_present"] is True


def test_exact_declared_source_remains_readable_in_home_checkout(release_case):
    # Arrange
    case = release_case
    # Act
    result = execute(case, mode="source_read")
    # Assert
    assert result.returncode == 0 and json.loads(result.stdout)["source_read"] is True


def test_private_home_is_refused_despite_source_and_interpreter_read_allowance(release_case):
    # Arrange
    case = release_case
    # Act
    result = execute(case, mode="private_read")
    # Assert
    assert result.returncode != 0 and "release probe refuses personal state" in result.stderr


def test_declared_source_allowance_never_permits_writing(release_case):
    # Arrange
    case = release_case
    target = ROOT / "src/qualification-refused-write"
    if target.exists():
        raise RuntimeError("refused-write fixture target already exists")
    # Act
    result = execute(case, mode="source_write")
    # Assert
    assert (result.returncode != 0 and "release probe refuses" in result.stderr
            and not target.exists())


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
        env=environment, cwd=ROOT, capture_output=True, text=True, check=False,
    )
    # Assert
    assert (result.returncode, "invalid-publisher" in result.stdout,
            "owned-response-field-not-for-log" in result.stdout) == (1, True, False)


def test_real_source_ci_format_handles_ambient_debug_without_findings(release_case):
    # Arrange
    scratch, private, probe, environment = release_case
    runner = (ROOT / ".github/ci/run-in-sif.sh").read_text()
    declarations = "\n".join(line for line in runner.splitlines()
                             if line.startswith("export SCITEX_LOGGING_FORMAT="))
    command = """set -euo pipefail
source "$1"
scitex_release_context "$2" "$3"
SCITEX_LOGGING_FORMAT=debug
""" + declarations + """
scitex_release_run env SCITEX_LOGGING_FORMAT="$SCITEX_LOGGING_FORMAT" "$4" "$5" "$6" audit "$7"
"""
    # Act
    result = subprocess.run(
        ["bash", "-c", command, "source-audit", str(CONTEXT), str(scratch),
         str(Path(sys.executable).parent.parent), sys.executable, str(probe),
         str(private), str(ROOT / "src")],
        env=environment, cwd=ROOT, capture_output=True, text=True, check=False,
    )
    report = json.loads(result.stdout) if result.returncode == 0 else {}
    # Assert
    assert (result.returncode, report.get("audit_result")) == (0, [0, True, 0]), result.stderr


def execute_source_launcher(case, mode="environment"):
    """Execute actual source-launcher declarations and application prefix."""
    scratch, private, probe, environment = case
    runner = (ROOT / ".github/ci/run-in-sif.sh").read_text()
    launch = next(line for line in runner.splitlines()
                  if line.startswith(("scitex_test_run nice ", "nice -n ")))
    prefix = launch.rstrip().removesuffix("\\").rstrip()
    function = ""
    if "scitex_test_run() {" in runner:
        function = "scitex_test_run() {" + runner.split("scitex_test_run() {", 1)[1].split("\n}", 1)[0] + "\n}\n"
    initialize = ""
    if 'scitex_release_context "$TMPDIR" "$VENV"' in runner:
        initialize = 'source "$1"\nscitex_release_context "$TMPDIR" "$VENV"\n'
    command = """set -euo pipefail
TMPDIR="$2"
VENV="$3"
PGDIR="$TMPDIR/postgres"
MPLCONFIGDIR="$TMPDIR/mpl"
export SCITEX_STORE_DSN="$9"
""" + initialize + function + prefix + ' "$4" "$5" "$6" "$7" "$8"\n'
    from urllib.parse import quote
    dsn = "postgresql://postgres@" + quote(str(scratch / "postgres"), safe="") + "/postgres"
    return subprocess.run(
        ["bash", "-c", command, "source-launcher-probe", str(CONTEXT), str(scratch),
         str(Path(sys.executable).parent.parent), sys.executable, str(probe),
         str(private), mode, str(ROOT / "src"), dsn],
        env=environment, cwd=ROOT, capture_output=True, text=True, check=False,
    )


def test_source_launcher_imports_use_owned_daily_log_and_private_socket(release_case):
    # Arrange
    case = release_case
    # Act
    result = execute_source_launcher(case, mode="source")
    report = json.loads(result.stdout) if result.returncode == 0 else {}
    # Assert
    assert (result.returncode, report.get("entrypoint_callable"),
            report.get("daily_log_owned"), report.get("store_owned_socket")) == (0, True, True, True), result.stderr


def test_source_launcher_rejects_ambient_provider_and_loader_overrides(release_case):
    # Arrange
    case = release_case
    # Act
    result = execute_source_launcher(case)
    report = json.loads(result.stdout)
    # Assert
    assert (report["ambient_without_loader"], report["loader_paths"]) == (
        False, [str(case[0] / "site"), str(ROOT / "src")])


def test_source_launcher_state_paths_stay_in_job_scratch(release_case):
    # Arrange
    case = release_case
    scratch = case[0]
    # Act
    result = execute_source_launcher(case)
    report = json.loads(result.stdout)
    # Assert
    assert all(value and (Path(value) == scratch or scratch in Path(value).parents)
               for value in report["paths"].values())
