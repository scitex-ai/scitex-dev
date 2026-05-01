#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for ``scitex-dev skills self-explain`` (issue: skills self-explain CLI).

Docker / claude API calls are mocked — never invoked for real in tests.
"""

from __future__ import annotations

import subprocess

import pytest


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


def test_module_imports_and_exports_callable():
    from scitex_dev._cli.skills import _self_explain

    assert callable(_self_explain.self_explain)
    # Canonical prompts are exposed as constants for greppability.
    assert isinstance(_self_explain._PROMPT_WHAT_FOR, str)
    assert isinstance(_self_explain._PROMPT_PROBLEMS, str)
    assert isinstance(_self_explain._PROMPT_QUICK_START, str)


# ---------------------------------------------------------------------------
# Mocked end-to-end
# ---------------------------------------------------------------------------


class _FakeRunner:
    """Returns a canned response per prompt; mirrors NewbieDockerRunner.run shape."""

    def __init__(self):
        self.calls = []

    def run(self, prompt, *, model="claude-haiku-4-5", timeout=120):
        self.calls.append((prompt, model))
        if "ONE sentence" in prompt:
            return {"result": "It loads and saves data in 30+ formats."}
        if "3-5 problems" in prompt:
            return {
                "result": (
                    "| # | Problem | Solution |\n"
                    "|---|---------|----------|\n"
                    "| 1 | Format zoo | One save() call |\n"
                )
            }
        if "Quick Start" in prompt:
            return {"result": "```python\nimport scitex.io as sio\n```"}
        return {"result": "unexpected prompt"}

    def close(self):
        pass


def test_self_explain_returns_expected_keys(monkeypatch, tmp_path):
    from scitex_dev._cli.skills import _self_explain

    # Stub out skill-tree resolution so we don't need a real package layout.
    monkeypatch.setattr(_self_explain, "_find_skills_dir", lambda dist: tmp_path)

    runner = _FakeRunner()
    result = _self_explain.self_explain("scitex-io", _runner=runner)

    assert result["package"] == "scitex-io"
    assert "what_for" in result
    assert "problems_solved" in result
    assert "quick_start" in result
    assert "30+ formats" in result["what_for"]
    assert "| # | Problem | Solution |" in result["problems_solved"]
    assert "scitex.io" in result["quick_start"]
    # All three prompts were sent, model propagated.
    assert len(runner.calls) == 3
    assert all(call[1] == "claude-haiku-4-5" for call in runner.calls)


def test_self_explain_runs_per_prompt_returns_lists(monkeypatch, tmp_path):
    from scitex_dev._cli.skills import _self_explain

    monkeypatch.setattr(_self_explain, "_find_skills_dir", lambda dist: tmp_path)

    runner = _FakeRunner()
    result = _self_explain.self_explain("scitex-io", runs_per_prompt=2, _runner=runner)

    assert isinstance(result["what_for"], list)
    assert len(result["what_for"]) == 2
    # 3 prompts × 2 runs.
    assert len(runner.calls) == 6


def test_unknown_distribution_raises():
    from scitex_dev._cli.skills import _self_explain

    with pytest.raises(ValueError):
        _self_explain.self_explain("definitely-not-a-real-pkg")


# ---------------------------------------------------------------------------
# CLI surface (CliRunner via the `scitex-dev` console_script)
# ---------------------------------------------------------------------------


def test_cli_help_shows_example_block():
    """audit-cli §4: help text must include a concrete Example block."""
    r = subprocess.run(
        ["scitex-dev", "skills", "self-explain", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "Example" in out
    assert "scitex-dev skills self-explain" in out
    # §2: the --json flag must be advertised.
    assert "--json" in out


def test_cli_help_mentions_distribution_arg():
    r = subprocess.run(
        ["scitex-dev", "skills", "self-explain", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0
    assert "DISTRIBUTION" in r.stdout


# EOF
