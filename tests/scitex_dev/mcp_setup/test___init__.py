"""Owned real files exercise safe client setup without running MCP tools."""

import json
import os
import stat
import subprocess
import sys

import pytest
from concurrent.futures import ThreadPoolExecutor

from scitex_dev.mcp_setup import build_mcp_install_manifest, install_mcp_client_config


def _manifest(name="owned"):
    return build_mcp_install_manifest(name, command="owned-command", args=["mcp", "start"])


def test_leaf_manifest_is_json_client_compatible():
    # Arrange
    manifest = _manifest()
    # Act
    result = json.loads(json.dumps(manifest))
    # Assert
    assert (result["client_config"], result["runtime_verified"]) == (
        {"mcpServers": {"owned": {"command": "owned-command", "args": ["mcp", "start"]}}}, False
    )


def test_dry_run_creates_neither_parent_config_nor_lock(tmp_path):
    # Arrange
    target = tmp_path / "absent" / ".mcp.json"
    # Act
    result = install_mcp_client_config(_manifest()["client_config"], target, dry_run=True)
    # Assert
    assert (result["changed"], result["dry_run"], target.parent.exists()) == (True, True, False)


def test_install_preserves_foreign_values_and_is_idempotent(tmp_path):
    # Arrange
    target = tmp_path / "mcp.json"
    foreign = {"settings": {"owned-secret-sentinel": "do-not-print"},
               "mcpServers": {"foreign": {"command": "keep", "env": {"KEY": "private-sentinel"}}}}
    target.write_text(json.dumps(foreign))
    # Act
    first = install_mcp_client_config(_manifest()["client_config"], target)
    after = target.read_bytes()
    second = install_mcp_client_config(_manifest()["client_config"], target)
    config = json.loads(after)
    observed = (first["changed"], second["changed"], after == target.read_bytes(),
                config["settings"] == foreign["settings"],
                config["mcpServers"]["foreign"] == foreign["mcpServers"]["foreign"],
                "private-sentinel" in json.dumps(first), "do-not-print" in json.dumps(second))
    # Assert
    assert observed == (True, False, True, True, True, False, False)


def test_same_server_conflict_refuses_before_any_change(tmp_path):
    # Arrange
    target = tmp_path / "mcp.json"
    target.write_text('{"mcpServers":{"owned":{"command":"foreign-command"}}}')
    original = target.read_bytes()
    # Act
    error = None
    try:
        install_mcp_client_config(_manifest()["client_config"], target)
    except ValueError as exc:
        error = str(exc)
    observed = (error is not None and "different configuration" in error,
                target.read_bytes() == original)
    # Assert
    assert observed == (True, True)


def test_invalid_existing_json_is_not_overwritten(tmp_path):
    # Arrange
    target = tmp_path / "mcp.json"
    target.write_text("{not-json")
    # Act
    refused = False
    try:
        install_mcp_client_config(_manifest()["client_config"], target)
    except ValueError:
        refused = True
    observed = (refused, target.read_text())
    # Assert
    assert observed == (True, "{not-json")


def test_concurrent_shared_installs_preserve_both_servers(tmp_path):
    # Arrange
    target = tmp_path / "mcp.json"
    fragments = [_manifest(name)["client_config"] for name in ["owned-a", "owned-b"]]
    # Act
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda fragment: install_mcp_client_config(fragment, target), fragments))
    config = json.loads(target.read_text())
    # Assert
    assert set(config["mcpServers"]) == {"owned-a", "owned-b"}


def test_symlink_config_is_not_replaced_or_followed(tmp_path):
    # Arrange
    original = tmp_path / "real.json"
    original.write_text('{"sentinel":"owned-original"}')
    link = tmp_path / "linked.json"
    link.symlink_to(original)
    # Act
    refused = False
    try:
        install_mcp_client_config(_manifest()["client_config"], link)
    except ValueError:
        refused = True
    observed = (refused, link.is_symlink(), original.read_text())
    # Assert
    assert observed == (True, True, '{"sentinel":"owned-original"}')


def test_invalid_fragment_cannot_create_client_config(tmp_path):
    # Arrange
    target = tmp_path / "absent" / "mcp.json"
    invalid = {"mcpServers": {"owned": {"command": "python", "args": "shell text"}}}
    # Act
    refused = False
    try:
        install_mcp_client_config(invalid, target)
    except ValueError:
        refused = True
    observed = (refused, target.parent.exists())
    # Assert
    assert observed == (True, False)


@pytest.fixture(params=[(adapter, dry, old, new) for adapter in ['api', 'cli'] for dry in [False, True] for old, new in [(0o644, 0o600), (0o600, 0o640), (0o640, 0o400), (0o600, 0o600), (0o640, 0o640), (0o644, 0o644)]])
def config_mode_case(request, tmp_path):
    adapter, dry, old_mode, new_mode = request.param
    root = tmp_path / 'owned-client'
    root.mkdir()
    target, sentinel = root / 'client.json', root / 'sentinel.txt'
    original = {'settings': {'marker': 'owned-private-value'}, 'mcpServers': {'foreign': {'command': 'kept-command', 'args': []}}}
    target.write_text(json.dumps(original))
    target.chmod(old_mode)
    sentinel.write_bytes(b'unrelated sibling\n')
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns, stat.S_IMODE(f.stat().st_mode)) for f in [target, sentinel]]
    yield root, target, sentinel, adapter, dry, old_mode, new_mode, original, before


def test_config_mode_change_is_preserved_or_dry_run_is_inert(config_mode_case):
    # Arrange
    root, target, sentinel, adapter, dry, old_mode, new_mode, original, before = config_mode_case
    code = """
from pathlib import Path
import contextlib,io,json,os,sys
from scitex_dev.mcp_setup import build_mcp_install_manifest,install_mcp_client_config
if sys.argv[2]=='cli':
    import click
    from scitex_dev._cli import main
path=Path(sys.argv[1]);adapter=sys.argv[2];dry=sys.argv[3]=='True';new_mode=int(sys.argv[4]);event={'called':False}
def observe(event_name,args):
    if event_name=='tempfile.mkstemp' and not event['called'] and Path(args[0]).parent==path.parent:
        event['called']=True
        path.chmod(new_mode)
sys.addaudithook(observe)
result=None;error=None
expected_error=ValueError if adapter=='api' else click.ClickException
try:
    if adapter=='api':
        manifest=build_mcp_install_manifest('owned',command='owned-command',args=['mcp','start'])
        result=install_mcp_client_config(manifest['client_config'],path,dry_run=dry)
    else:
        output,diagnostic=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(output),contextlib.redirect_stderr(diagnostic):
            main.main(args=['mcp','install','--config',str(path),'--json']+(['--dry-run'] if dry else []),prog_name='scitex-dev',standalone_mode=False)
        result=json.loads(output.getvalue())['installation']
except expected_error as exc:
    error=str(exc)
print(json.dumps({'hook_called':event['called'],'refused':error is not None,'changed_message':bool(error and 'changed during installation' in error),'result':result,'leaked_value':'owned-private-value' in json.dumps(result)}))
"""
    # Act
    completed = subprocess.run([sys.executable, '-I', '-c', code, str(target), adapter, str(dry), str(new_mode)], cwd=root, env=os.environ.copy(), check=True, capture_output=True, timeout=15)
    outcome = json.loads(completed.stdout)
    current = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns, stat.S_IMODE(f.stat().st_mode)) for f in [target, sentinel]]
    refused = not dry and old_mode != new_mode
    if dry or refused:
        expected_mode = old_mode if dry else new_mode
        correct_target = current[0] == (*before[0][:3], expected_mode)
    else:
        merged = json.loads(current[0][0])
        server = 'owned' if adapter == 'api' else 'scitex-dev'
        correct_target = merged['settings'] == original['settings'] and merged['mcpServers']['foreign'] == original['mcpServers']['foreign'] and set(merged['mcpServers']) == {'foreign', server} and current[0][3] == old_mode
    expected_files = {'client.json', 'sentinel.txt'} | (set() if dry else {'.client.json.scitex-mcp.lock'})
    correct_result = outcome['changed_message'] if refused else outcome['result']['changed'] and outcome['result']['dry_run'] == dry and outcome['result']['runtime_verified'] is False
    # Assert
    assert (outcome['refused'], outcome['hook_called'], correct_target, current[1], {f.name for f in root.iterdir()}, correct_result, outcome['leaked_value']) == (refused, not dry, True, before[1], expected_files, True, False)
