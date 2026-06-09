"""Load and validate ~/.scitex/dev/ci-runner.yaml."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

_DEFAULT_CONFIG_PATH = Path.home() / ".scitex" / "dev" / "ci-runner.yaml"


def _resolve_config_path() -> Path:
    """Return the config path following the precedence contract.

    Precedence:
      $SCITEX_DEV_CONFIG → $XDG_CONFIG_HOME/scitex/dev/ci-runner.yaml → ~/.scitex/dev/ci-runner.yaml
    """
    env = os.environ.get("SCITEX_DEV_CONFIG")
    if env:
        return Path(env)

    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        candidate = Path(xdg) / "scitex" / "dev" / "ci-runner.yaml"
        if candidate.exists():
            return candidate

    return _DEFAULT_CONFIG_PATH


def load_runner_config() -> dict[str, Any]:
    """Load + validate the ci-runner config.

    Each required key MUST be present — no defaults.
    Raises SystemExit if required keys are missing.
    """
    cfg_path = _resolve_config_path()
    if not cfg_path.exists():
        raise SystemExit(
            f"missing private config at {cfg_path}; "
            f"run: scitex-dev ci runner onboard … to get started, or create "
            f"~/.scitex/dev/ci-runner.yaml with your bindings"
        )

    try:
        import yaml
    except ImportError:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")

    with cfg_path.open() as fh:
        cfg = yaml.safe_load(fh) or {}

    required = [
        ("hpc", "user"),
        ("hpc", "ssh_host"),
        ("hpc", "apptainer"),
        ("hpc", "sif"),
        ("runner", "name"),
        ("runner", "labels"),
        ("runner", "home"),
        ("runner", "wrap_log"),
        ("ci_lease", "jobname"),
        ("ci_lease", "sbatch_script"),
        ("ci_lease", "renew_threshold_min"),
        ("github", "pat_env"),
        ("github", "default_repo"),
        ("github", "variable_name"),
        ("watchdog", "poll_interval_sec"),
        ("watchdog", "offline_grace_min"),
        ("watchdog", "alert_via"),
    ]
    for path in required:
        node = cfg
        for k in path:
            if not isinstance(node, dict) or k not in node:
                raise SystemExit(
                    f"missing config key: {'.'.join(path)} in {cfg_path}"
                )
            node = node[k]

    return cfg


def _ssh_target(cfg: dict[str, Any]) -> str:
    """Return ``user@ssh_host`` from config."""
    return f"{cfg['hpc']['user']}@{cfg['hpc']['ssh_host']}"


def get_gh_token(cfg: dict[str, Any]) -> str:
    """Read the GitHub PAT from the env var named in config."""
    env_name = cfg["github"]["pat_env"]
    token = os.environ.get(env_name)
    if not token:
        raise SystemExit(
            f"environment variable {env_name!r} is not set. "
            f"Set it to a classic PAT with repo + workflow + "
            f"actions:variables:write scopes."
        )
    return token


def _gh_api(cfg: dict[str, Any], method: str, path: str, data: dict | None = None) -> dict:
    """Call GitHub REST API via gh CLI. Returns parsed JSON."""
    token = get_gh_token(cfg)
    repo = cfg["github"]["default_repo"]
    url = f"https://api.github.com/repos/{repo}/{path.lstrip('/')}"

    cmd = ["gh", "api", url, "-X", method, "--jq", "."]
    if data is not None:
        # gh api -f key=value pairs
        for k, v in data.items():
            cmd.extend(["-f", f"{k}={v}"])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise SystemExit(f"gh api {method} {path} failed: {result.stderr.strip()}")

    import json

    try:
        return json.loads(result.stdout.strip()) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        raise SystemExit(f"gh api returned non-JSON: {result.stdout!r}")


def ssh_run(cfg: dict[str, Any], cmd: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run a command via ssh on the HPC host."""
    target = _ssh_target(cfg)
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "ControlPath=none",
            "-o",
            "ControlMaster=no",
            target,
            cmd,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result
