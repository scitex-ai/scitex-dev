"""Smoke tests for the ``NewbieDockerRunner`` backend.

Skipped unless:
  - ``SCITEX_AGENT_CONTAINER_CI_ANTHROPIC_API_KEY`` is set
  - ``docker version`` succeeds
  - The configured image is locally available
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from scitex_dev._agentic_testing import (
    DEFAULT_DOCKER_IMAGE,
    NewbieDockerRunner,
)


def _docker_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "version"], capture_output=True, check=True, timeout=10
        )
    except Exception:
        return False
    image = os.environ.get("SCITEX_DEV_AGENTIC_DOCKER_IMAGE", DEFAULT_DOCKER_IMAGE)
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            timeout=10,
        )
        return proc.returncode == 0
    except Exception:
        return False


_SKIP_REASON = (
    "requires SCITEX_AGENT_CONTAINER_CI_ANTHROPIC_API_KEY + working docker + image"
)
_should_skip = not (
    os.environ.get("SCITEX_AGENT_CONTAINER_CI_ANTHROPIC_API_KEY") and _docker_ok()
)


pytestmark = [
    pytest.mark.docker_smoke,
    pytest.mark.slow,
    pytest.mark.skipif(_should_skip, reason=_SKIP_REASON),
]


def _cache_creation(result: dict) -> int:
    usage = result.get("usage") or {}
    v = usage.get("cache_creation_input_tokens", 0)
    return int(v) if isinstance(v, (int, float)) else 0


def _cost(result: dict) -> float:
    for key in ("total_cost_usd", "cost_usd"):
        v = result.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    usage = result.get("usage") or {}
    for key in ("total_cost_usd", "cost_usd"):
        v = usage.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def test_docker_backend_hello():
    runner = NewbieDockerRunner()
    try:
        result = runner.run("hello")
    finally:
        runner.close()

    assert result.get("type") == "result"
    assert result.get("is_error") is False
    cost = _cost(result)
    assert cost > 0.0, f"cost should be reported, got {cost}"
    assert cost < 0.05, f"cost too high ({cost}); sanity bound"
    cache_create = _cache_creation(result)
    assert cache_create < 8000, (
        f"cache_creation_input_tokens={cache_create} is unexpectedly large "
        "for a clean-slate newbie container"
    )


def test_docker_backend_closes_cleanly():
    runner = NewbieDockerRunner()
    runner.run("hello")
    name = runner.container_name
    runner.close()
    proc = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert name not in proc.stdout.splitlines(), (
        f"container {name} still present after close():\n{proc.stdout}"
    )
