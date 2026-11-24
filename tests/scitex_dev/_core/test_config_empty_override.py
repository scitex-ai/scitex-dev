"""Real isolated reads keep path reporting and configuration selection consistent."""

import json
import os
import subprocess
import sys

import pytest


@pytest.fixture(params=[(scope, mode) for scope in ['user', 'project', 'legacy'] for mode in ['absent', 'empty', 'explicit-env', 'explicit-argument', 'empty-state']])
def empty_override_case(request, tmp_path):
    scope, mode = request.param
    root = tmp_path / 'owned-config'
    root.mkdir()
    home = root / 'home'
    home.mkdir()
    cwd = root / 'project' / 'nested'
    cwd.mkdir(parents=True)
    state_root = root / 'user-state'
    default = state_root / ('dev_config.yaml' if scope == 'legacy' else 'dev/config.yaml')
    if scope == 'project':
        subprocess.run(['git', 'init', str(cwd.parent)], check=True, capture_output=True, timeout=10)
        default = cwd.parent / '.scitex/dev/config.yaml'
    env_file, argument_file, state_file = root / 'env.yaml', root / 'argument.yaml', root / 'state.json'
    for path, label in [(default, scope), (env_file, 'environment'), (argument_file, 'argument')]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'branches: [{label}]\npackages:\n  - name: scitex-dev\n    cli_enabled: false\n    skills_enabled: false\n    mcp_enabled: false\n')
    state_file.write_text(json.dumps({'cli': {'scitex-dev': True}} if mode == 'empty-state' else {}))
    sentinel = root / 'sentinel.txt'
    sentinel.write_bytes(b'unrelated config sentinel\n')
    protected = [default, env_file, argument_file, state_file, sentinel]
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in protected]
    env = {**os.environ, 'HOME': str(home), 'SCITEX_DIR': str(state_root), 'SCITEX_DEV_KNOB_STATE': str(state_file)}
    env.pop('SCITEX_DEV_CONFIG', None)
    if mode in ['empty', 'empty-state']:
        env['SCITEX_DEV_CONFIG'] = ''
    elif mode in ['explicit-env', 'explicit-argument']:
        env['SCITEX_DEV_CONFIG'] = str(env_file)
    argument = str(argument_file) if mode == 'explicit-argument' else ''
    selected = env_file if mode in ['explicit-env', 'explicit-argument'] else default
    policy_path = argument_file if argument else selected
    label = 'argument' if argument else ('environment' if mode == 'explicit-env' else scope)
    yield cwd, env, argument, selected, policy_path, label, mode == 'empty-state', protected, before


def test_empty_override_preserves_default_and_explicit_selection(empty_override_case):
    # Arrange
    cwd, env, argument, selected, policy_path, label, cli_enabled, protected, before = empty_override_case
    code = """
import json,sys
from scitex_dev import get_config_path,load_config
from scitex_dev.exposure import load_exposure_policy
config=load_config(sys.argv[1] if sys.argv[1] else None)
row=next(p for p in config.packages if p.name=='scitex-dev')
policy=load_exposure_policy(sys.argv[1] if sys.argv[1] else None)
print(json.dumps({'reported':str(get_config_path()),'policy_path':str(policy.config_path),'branches':config.branches,'loaded':[row.cli_enabled,row.skills_enabled,row.mcp_enabled],'snapshot':[policy.is_enabled('scitex-dev',s) for s in ['cli','skills','mcp']]}))
"""
    expected = {'reported': str(selected), 'policy_path': str(policy_path), 'branches': [label], 'loaded': [cli_enabled, False, False], 'snapshot': [cli_enabled, False, False]}
    # Act
    result = subprocess.run([sys.executable, '-I', '-c', code, argument], cwd=cwd, env=env, check=True, capture_output=True, timeout=15)
    after = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in protected]
    # Assert
    assert (json.loads(result.stdout), after) == (expected, before)
