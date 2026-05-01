#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex-dev's ``skills self-explain`` wrapper.

The implementation is upstream in ``newb`` (tested there). These tests
exercise the scitex-dev value-add: distribution-name → ``_skills/<dist>/``
resolution and delegation into ``newb.self_explain``.
"""

from __future__ import annotations

import subprocess

import pytest


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


def test_module_imports_and_exports_callables():
    from scitex_dev._cli.skills import _self_explain

    assert callable(_self_explain.self_explain)
    # render_markdown is re-exported from newb so existing CLI imports work.
    assert callable(_self_explain.render_markdown)
    assert callable(_self_explain._find_skills_dir)


# ---------------------------------------------------------------------------
# Distribution resolution (the scitex-dev-specific bit)
# ---------------------------------------------------------------------------


def test_unknown_distribution_raises():
    from scitex_dev._cli.skills import _self_explain

    with pytest.raises(ValueError, match="Unknown distribution"):
        _self_explain._find_skills_dir("definitely-not-a-real-pkg")


def test_find_skills_dir_returns_skills_subdir(monkeypatch, tmp_path):
    """Resolver returns ``<local>/src/<import_name>/_skills/<dist>/``."""
    from scitex_dev._cli.skills import _self_explain

    # Build a fake checkout layout.
    dist = "scitex-demo"
    import_name = "scitex_demo"
    local = tmp_path / "checkout"
    skills_dir = local / "src" / import_name / "_skills" / dist
    skills_dir.mkdir(parents=True)
    (skills_dir / "00.md").write_text("# demo\n")

    # Patch the ecosystem registry the resolver consults.
    from scitex_dev import _ecosystem

    monkeypatch.setitem(
        _ecosystem.ECOSYSTEM,
        dist,
        {"import_name": import_name, "local_path": str(local)},
    )
    monkeypatch.setattr(
        _ecosystem, "get_local_path", lambda d: local if d == dist else None
    )

    resolved = _self_explain._find_skills_dir(dist)
    assert resolved == skills_dir
    assert resolved.is_dir()


# ---------------------------------------------------------------------------
# Delegation: self_explain wires distribution → newb.self_explain correctly
# ---------------------------------------------------------------------------


class _FakeRunner:
    """Minimal runner stub matching newb's contract."""

    def __init__(self):
        self.calls = []

    def run(self, prompt, *, model="claude-haiku-4-5", timeout=120):
        self.calls.append((prompt, model))
        return {"result": "stub answer"}

    def close(self):
        pass


def test_self_explain_resolves_then_delegates(monkeypatch, tmp_path):
    """scitex-dev's wrapper must resolve distribution → skills_dir → newb."""
    from scitex_dev._cli.skills import _self_explain

    # Stage a skills dir whose .name == the distribution (so newb's payload
    # populates ``"package": "scitex-io"`` for free).
    skills_dir = tmp_path / "scitex-io"
    skills_dir.mkdir()
    (skills_dir / "demo.md").write_text("# demo\n")

    monkeypatch.setattr(_self_explain, "_find_skills_dir", lambda dist: skills_dir)

    runner = _FakeRunner()
    result = _self_explain.self_explain(
        "scitex-io", _runner=runner, model="claude-haiku-4-5"
    )

    # newb populated package from skills_dir.name (== distribution name).
    assert result["package"] == "scitex-io"
    # Each canonical prompt landed in the runner exactly once (runs_per_prompt=1).
    assert len(runner.calls) >= 1
    assert all(call[1] == "claude-haiku-4-5" for call in runner.calls)


def test_self_explain_runs_per_prompt_propagates(monkeypatch, tmp_path):
    """The runs_per_prompt kwarg must be forwarded to newb."""
    from scitex_dev._cli.skills import _self_explain

    skills_dir = tmp_path / "scitex-io"
    skills_dir.mkdir()
    (skills_dir / "demo.md").write_text("# demo\n")
    monkeypatch.setattr(_self_explain, "_find_skills_dir", lambda dist: skills_dir)

    runner = _FakeRunner()
    result = _self_explain.self_explain("scitex-io", runs_per_prompt=2, _runner=runner)

    # With runs_per_prompt=2, newb returns lists for each prompt key.
    assert isinstance(result["what_for"], list)
    assert len(result["what_for"]) == 2


# ---------------------------------------------------------------------------
# CLI surface (still owned by scitex-dev's _manage.py)
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
