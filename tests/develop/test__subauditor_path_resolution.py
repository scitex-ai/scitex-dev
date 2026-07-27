"""Proof: audit-cli / audit-mcp-tools / audit-skills root at ``--path``.

The audit-all wrong-tree footgun (operator directive 2026-07-21): three
of the six sub-auditors used to resolve their target tree via the
registry / import-location (the operator's ``~/proj/<pkg>`` develop
checkout on CI) instead of the ``--path`` the caller passed — grading a
DIFFERENT tree while reporting as if they graded the PR. These tests show
the fix: given an explicit checkout at a path that is NOT the registry /
install location, each newly-path-aware sub-auditor resolves THAT tree.

This is a CROSS-CUTTING integration test (skills + mcp + cli) that
mirrors no single ``src/`` module, so it lives under ``tests/develop/``
(alongside the ``test_audit.py`` exemplar) — the integration-test
location PS-204's orphan-test-file rule scans past (PS-204 only walks
``tests/<pkg>/``).

PA-306 no-mocks: every test builds a REAL temp checkout (``tmp_path``)
and calls the real resolver / auditor entry points — no monkeypatch, no
mocker. The two banner tests capture the ``scitex_dev.audit`` INFO record
by attaching their OWN handler to that logger (its module handler binds
to the real ``sys.stderr`` at import time, so ``capsys`` misses it in
xdist order — the same flake documented in
``_cli/audit/_project/test__resolved_tree.py``). PA-307 test-quality:
``# Arrange`` / ``# Act`` / ``# Assert`` markers, one assertion per test.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path


def _logger_banner(run) -> str:
    """Run ``run()`` and return the ``scitex_dev.audit`` log text it emits.

    The resolved-tree banner is a scitex-logging INFO record whose module
    handler is bound to the REAL ``sys.stderr`` at import time, so
    ``capsys`` / ``redirect_stderr`` capture nothing under xdist ordering.
    Attaching a handler to the exact ``scitex_dev.audit`` logger captures
    the record deterministically regardless of global handler state.
    """
    banner = io.StringIO()
    handler = logging.StreamHandler(banner)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("scitex_dev.audit")
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        run()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)
    return banner.getvalue()


# ---------------------------------------------------------------------------
# audit-skills — the skills tree is read from `<--path>/src/<pkg>/_skills/`
# ---------------------------------------------------------------------------


def _make_skills_checkout(root: Path, distribution: str) -> Path:
    """Real checkout with a valid `src/<import_name>/_skills/<dist>/` tree."""
    import_name = distribution.replace("-", "_")
    skills = root / "src" / import_name / "_skills" / distribution
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n# Demo\n", encoding="utf-8"
    )
    return skills


def test_audit_skills_repo_root_resolves_skills_dir_under_path(tmp_path, capsys):
    """audit_skills(repo_root=--path) reads `_skills/` from THAT tree."""
    # Arrange
    dist = "demo-skillpkg"
    skills = _make_skills_checkout(tmp_path, dist)
    from scitex_dev._cli.audit._skills._audit import audit_skills

    # Act
    audit_skills(dist, json_out=True, repo_root=tmp_path)
    data = json.loads(capsys.readouterr().out)
    # Assert
    assert data["skills_dir"] == str(skills)


def test_audit_skills_repo_root_is_not_the_install_location(tmp_path, capsys):
    """The resolved skills_dir is under --path, never site-packages."""
    # Arrange
    dist = "demo-skillpkg"
    _make_skills_checkout(tmp_path, dist)
    from scitex_dev._cli.audit._skills._audit import audit_skills

    # Act
    audit_skills(dist, json_out=True, repo_root=tmp_path)
    data = json.loads(capsys.readouterr().out)
    # Assert
    assert str(tmp_path) in (data["skills_dir"] or "")


def test_audit_skills_repo_root_banner_names_the_path(tmp_path):
    """The human-rail resolved-tree banner announces the --path checkout."""
    # Arrange
    dist = "demo-skillpkg"
    _make_skills_checkout(tmp_path, dist)
    from scitex_dev._cli.audit._skills._audit import audit_skills

    # Act
    text = _logger_banner(
        lambda: audit_skills(
            dist, json_out=False, repo_root=tmp_path, resolved_via="explicit"
        )
    )
    # Assert
    assert str(tmp_path) in text


# ---------------------------------------------------------------------------
# audit-cli — the static §2 / §11 source scans root at `--path`
# ---------------------------------------------------------------------------


def test_audit_cli_repo_scan_flags_argparse_under_path(tmp_path):
    """§11: argparse in the --path checkout's _cli tree is flagged."""
    # Arrange
    pkg = tmp_path / "src" / "demo_cli"
    (pkg / "_cli").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "_cli" / "__init__.py").write_text("import argparse\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo-cli"\nversion = "0"\n'
        '[project.scripts]\ndemo-cli = "demo_cli._cli:main"\n',
        encoding="utf-8",
    )
    from scitex_dev._cli.audit._summary._cli_repo_scans import scan_repo_source

    out: list = []
    # Act
    scan_repo_source("demo-cli", tmp_path, out)
    # Assert
    assert any(v.rule == "§11" for v in out)


def test_audit_cli_repo_scan_flags_interactive_prompt_under_path(tmp_path):
    """§2: click.confirm in the --path checkout source is flagged."""
    # Arrange
    pkg = tmp_path / "src" / "demo_cli2"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "cmds.py").write_text(
        "import click\n\n\ndef f():\n    click.confirm('ok?')\n", encoding="utf-8"
    )
    from scitex_dev._cli.audit._summary._cli_repo_scans import (
        check_no_interactive_prompts_under,
    )

    out: list = []
    # Act
    check_no_interactive_prompts_under("demo-cli2", tmp_path, out)
    # Assert
    assert any(v.rule == "§2" for v in out)


def test_audit_cli_repo_scan_clean_tree_yields_no_violations(tmp_path):
    """A --path checkout with Click + no prompts produces nothing (control)."""
    # Arrange
    pkg = tmp_path / "src" / "demo_cli3"
    (pkg / "_cli").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "_cli" / "__init__.py").write_text("import click\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo-cli3"\nversion = "0"\n'
        '[project.scripts]\ndemo-cli3 = "demo_cli3._cli:main"\n',
        encoding="utf-8",
    )
    from scitex_dev._cli.audit._summary._cli_repo_scans import scan_repo_source

    out: list = []
    # Act
    scan_repo_source("demo-cli3", tmp_path, out)
    # Assert
    assert out == []


def test_audit_cli_repo_scan_ignores_argparse_outside_the_path(tmp_path):
    """The scan reads ONLY the --path tree — a sibling tree is untouched."""
    # Arrange — the audited checkout is clean; a SEPARATE tree has argparse.
    audited = tmp_path / "audited"
    other = tmp_path / "other" / "src" / "demo_cli4"
    other.mkdir(parents=True)
    (other / "__init__.py").write_text("import argparse\n", encoding="utf-8")
    pkg = audited / "src" / "demo_cli4"
    (pkg / "_cli").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "_cli" / "__init__.py").write_text("import click\n", encoding="utf-8")
    (audited / "pyproject.toml").write_text(
        '[project]\nname = "demo-cli4"\nversion = "0"\n'
        '[project.scripts]\ndemo-cli4 = "demo_cli4._cli:main"\n',
        encoding="utf-8",
    )
    from scitex_dev._cli.audit._summary._cli_repo_scans import scan_repo_source

    out: list = []
    # Act — audit ONLY the `audited` path
    scan_repo_source("demo-cli4", audited, out)
    # Assert — the sibling's argparse must not leak in
    assert out == []


# ---------------------------------------------------------------------------
# audit-mcp-tools — §6 parity config is read from `--path`
# ---------------------------------------------------------------------------


def test_audit_mcp_reads_parity_exempt_from_path(tmp_path):
    """§6: `mcp_parity_exempt` is read from the --path checkout's pyproject."""
    # Arrange
    (tmp_path / "pyproject.toml").write_text(
        "[tool.scitex_dev]\nmcp_parity_exempt = true\n", encoding="utf-8"
    )
    from scitex_dev._cli.audit._summary._mcp_parity import is_mcp_parity_exempt

    # Act
    exempt = is_mcp_parity_exempt("demo-mcp", repo=tmp_path)
    # Assert
    assert exempt is True


def test_audit_mcp_parity_skips_section6_when_repo_declares_exempt(tmp_path):
    """`_check_api_parity(repo=--path)` honours the exemption from that tree."""
    # Arrange — a large tool/API mismatch that WOULD flag §6 if not exempt.
    (tmp_path / "pyproject.toml").write_text(
        "[tool.scitex_dev]\nmcp_parity_exempt = true\n", encoding="utf-8"
    )
    from scitex_dev._cli.audit._summary._mcp_parity import _check_api_parity

    out: list = []
    tools = {f"demo_orphan_{i}" for i in range(20)}
    # Act
    _check_api_parity("demo-mcp", tools, out, repo=tmp_path)
    # Assert — exemption read from --path suppressed every §6 finding
    assert out == []


def test_audit_mcp_run_banner_names_the_path(tmp_path):
    """run_audit_mcp(repo=--path) surfaces the resolved-tree banner."""
    # Arrange — an unimportable package: no MCP server, but the banner emits.
    from scitex_dev._cli.audit._summary._mcp_audit import run_audit_mcp

    # Act
    text = _logger_banner(
        lambda: run_audit_mcp(
            "demo-nonexistent-pkg", repo=tmp_path, resolved_via="explicit"
        )
    )
    # Assert
    assert str(tmp_path) in text
