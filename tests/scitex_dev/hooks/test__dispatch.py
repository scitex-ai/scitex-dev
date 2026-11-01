"""Exercise actual entry-point discovery and dispatch in a fresh interpreter."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def provider(tmp_path):
    module = tmp_path / "fixture_hooks.py"
    module.write_text("""import os
from scitex_dev.hooks import HookRule
def provide():
    return [HookRule(id='fixture.guard', rule='Reject fixture denial', reason='Integration test', event='pre-tool-use', severity=os.environ.get('SCITEX_HOOK_TEST_SEVERITY', 'deny'), matches=('Write',), provider='fixture-hooks', check='fixture_hooks:check')]
def check(payload):
    return ['fixture denied'] if payload['tool_input']['content'] == 'deny' else []
""")
    metadata = tmp_path / "fixture_hooks-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: fixture-hooks\nVersion: 1.0\n"
    )
    (metadata / "entry_points.txt").write_text(
        "[scitex_dev.hooks]\nfixture-hooks = fixture_hooks:provide\n"
    )
    source = Path(__file__).resolve().parents[3] / "src"
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "PYTHONPATH": os.pathsep.join([str(tmp_path), str(source)]),
        "SCITEX_DEV_NO_DRIFT_WARN": "1",
        "SCITEX_LOGGING_FORCE_COLOR": "0",
        "SCITEX_LOGGING_LEVEL": "INFO",
        "LANG": "C.UTF-8",
    }


@pytest.mark.parametrize(
    "provider_name,content,expected",
    [
        ("fixture-hooks", "deny", 2),
        ("fixture-hooks", "allow", 0),
        ("missing-provider", "allow", 2),
    ],
)
def test_real_discovered_provider_controls_native_hook_exit(
    provider, provider_name, content, expected
):
    # Arrange
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"content": content},
    }
    # Act
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scitex_dev.hooks.dispatch",
            "--provider",
            provider_name,
        ],
        input=json.dumps(payload),
        check=False,
        env=provider,
        capture_output=True,
        text=True,
    )
    # Assert
    assert result.returncode == expected and result.stdout == ""


def test_provider_install_is_idempotent_and_preserves_foreign_config(
    provider, tmp_path
):
    # Arrange
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Read"]},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Read",
                            "hooks": [{"type": "command", "command": "existing-check"}],
                        }
                    ]
                },
            }
        )
    )
    code = "from scitex_dev.hooks._install_provider import install_provider; from pathlib import Path; import sys; p=Path(sys.argv[1]); install_provider(p, provider='fixture-hooks'); before=p.read_bytes(); install_provider(p, provider='fixture-hooks'); assert p.read_bytes()==before"
    # Act
    subprocess.run(
        [sys.executable, "-c", code, str(path)],
        env=provider,
        check=True,
        capture_output=True,
        text=True,
    )
    config = json.loads(path.read_text())
    # Assert
    assert (
        config["permissions"],
        len(config["hooks"]["PreToolUse"]),
        config["hooks"]["PreToolUse"][0]["hooks"][0]["command"],
    ) == ({"allow": ["Read"]}, 2, "existing-check")


def test_provider_dry_run_does_not_create_configuration(provider, tmp_path):
    # Arrange
    path = tmp_path / "absent.json"
    code = "from scitex_dev.hooks._install_provider import install_provider; import sys; install_provider(sys.argv[1], provider='fixture-hooks', dry_run=True)"
    # Act
    subprocess.run(
        [sys.executable, "-c", code, str(path)],
        env=provider,
        check=True,
        capture_output=True,
        text=True,
    )
    # Assert
    assert not path.exists()


def test_warning_rule_reports_without_blocking_the_tool(provider):
    # Arrange: severity belongs to the leaf, not the dispatcher.
    env = dict(provider, SCITEX_HOOK_TEST_SEVERITY="warn")
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"content": "deny"},
    }
    # Act
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scitex_dev.hooks.dispatch",
            "--provider",
            "fixture-hooks",
        ],
        input=json.dumps(payload),
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    # Assert
    assert result.returncode == 0 and result.stderr.count("fixture denied") == 1


def test_reinstallation_replaces_own_interpreter_and_keeps_a_shared_foreign_hook(
    provider, tmp_path
):
    # Arrange
    path = tmp_path / "settings.json"
    code = """from scitex_dev.hooks._install_provider import install_provider
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
install_provider(p, provider='fixture-hooks', python='/old/python')
data=json.loads(p.read_text())
data['hooks']['PreToolUse'][0]['hooks'].append({'type':'command', 'command':'foreign-hook'})
p.write_text(json.dumps(data))
install_provider(p, provider='fixture-hooks', python='/new/python')
"""
    # Act
    subprocess.run(
        [sys.executable, "-c", code, str(path)],
        env=provider,
        check=True,
        capture_output=True,
        text=True,
    )
    commands = [
        h["command"]
        for entry in json.loads(path.read_text())["hooks"]["PreToolUse"]
        for h in entry["hooks"]
    ]
    # Assert
    assert (
        len(commands) == 2
        and "foreign-hook" in commands
        and sum("/new/python" in c for c in commands) == 1
        and not any("/old/python" in c for c in commands)
    )


def test_install_preserves_configuration_symlink(provider, tmp_path):
    # Arrange
    target = tmp_path / "authored.json"
    target.write_text('{"permissions": {"allow": ["Read"]}}')
    link = tmp_path / "settings.json"
    link.symlink_to(target)
    code = "from scitex_dev.hooks._install_provider import install_provider; import sys; install_provider(sys.argv[1], provider='fixture-hooks')"
    # Act
    subprocess.run(
        [sys.executable, "-c", code, str(link)],
        env=provider,
        check=True,
        capture_output=True,
        text=True,
    )
    # Assert
    assert link.is_symlink() and "PreToolUse" in json.loads(target.read_text())["hooks"]


@pytest.mark.parametrize("payload", [[], {"tool_name": None}, {"tool_name": ""}])
def test_malformed_native_payload_cannot_pass_as_unmatched_tool(provider, payload):
    # Arrange
    command = [
        sys.executable,
        "-m",
        "scitex_dev.hooks.dispatch",
        "--provider",
        "fixture-hooks",
    ]
    # Act
    result = subprocess.run(
        command,
        input=json.dumps(payload),
        env=provider,
        text=True,
        capture_output=True,
        check=False,
    )
    # Assert
    assert result.returncode == 2


def test_missing_declared_script_cannot_claim_executable_coverage(provider, tmp_path):
    # Arrange
    module = tmp_path / "fixture_hooks.py"
    source = module.read_text().replace(
        "check='fixture_hooks:check'",
        "check='fixture_hooks:check', owner_module='fixture_hooks', script='missing.sh'",
    )
    module.write_text(source)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"content": "allow"},
    }
    # Act
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scitex_dev.hooks.dispatch",
            "--provider",
            "fixture-hooks",
        ],
        input=json.dumps(payload),
        env=provider,
        text=True,
        capture_output=True,
        check=False,
    )
    # Assert
    assert result.returncode == 2 and "unavailable script asset" in result.stderr


def test_explicit_native_hook_opt_out_is_not_overridden(provider, tmp_path):
    # Arrange
    settings = tmp_path / "settings.json"
    original = json.dumps({"disableAllHooks": True})
    settings.write_text(original)
    code = "from scitex_dev.hooks._install_provider import install_provider; import sys; install_provider(sys.argv[1],provider='fixture-hooks')"
    # Act
    result = subprocess.run(
        [sys.executable, "-c", code, str(settings)],
        env=provider,
        text=True,
        capture_output=True,
        check=False,
    )
    # Assert
    assert result.returncode != 0 and settings.read_text() == original


def test_configuration_receipt_never_claims_running_client_activation(
    provider, tmp_path
):
    # Arrange
    settings = tmp_path / "settings.json"
    code = "from scitex_dev.hooks._install_provider import install_provider; import json,sys; sys.stdout.write(json.dumps(install_provider(sys.argv[1],provider='fixture-hooks')))"
    # Act
    result = subprocess.run(
        [sys.executable, "-c", code, str(settings)],
        env=provider,
        text=True,
        capture_output=True,
        check=False,
    )
    receipt = json.loads(result.stdout)
    # Assert
    assert receipt["runtime_verified"] is False and receipt["blocking_events"] == [
        "pre-tool-use"
    ]
