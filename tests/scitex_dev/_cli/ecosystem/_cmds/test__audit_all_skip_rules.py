"""End-to-end: `audit-all` honours `audit.skip-rules`, loudly.

Uses the same no-mocks harness as `test__audit_all.py` — a real
executable named `scitex-dev` earlier on PATH, so audit-all really forks
subprocesses; they are just pointed at a stub we own.

The defect these tests exist to prevent: the per-repo pytest wrapper
honoured skip_rules while the org reusable workflow called `audit-all`
directly and did not, so develop was green while unified CI was red on
identical code (measured in scitex-hub PR #433).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


_DEFERRED_LINE = "ERRO:   [PS-139 §2] src/a.py: uses the legacy TQ helper"
_UNDECLARED_LINE = "ERRO:   [PS-999 §9] src/c.py: something nobody deferred"
_RATIONALE = "TQ-migration campaign, tracked in scitex-hub#412"


def _write_repo(root: Path, config_body: str | None) -> Path:
    """Create a minimal repo, optionally carrying an audit config."""
    repo = root / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    if config_body is not None:
        cfg = repo / ".scitex" / "dev" / "config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(config_body, encoding="utf-8")
    return repo


def _write_fake_scitex_dev(bin_dir: Path, *, failing_line: str | None) -> None:
    """Stub auditor: `audit-project` prints `failing_line` and exits 1."""
    body = f"""#!/usr/bin/env python3
import sys
argv = sys.argv[1:]
audit = argv[1] if len(argv) > 1 else ""
failing_line = {failing_line!r}
if audit == "audit-project" and failing_line:
    sys.stderr.write(failing_line + "\\n")
    sys.exit(1)
sys.stdout.write(f"STDOUT::{{audit}}\\n")
sys.exit(0)
"""
    script = bin_dir / "scitex-dev"
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run(
    tmp_path: Path,
    *,
    config_body: str | None,
    failing_line: str | None,
    as_json: bool = False,
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    _write_fake_scitex_dev(bin_dir, failing_line=failing_line)
    repo = _write_repo(tmp_path, config_body)

    @click.group()
    def main():
        pass

    register_ecosystem_commands(main)
    runner = CliRunner()
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    argv = [
        "ecosystem",
        "audit-all",
        "scitex-io",
        "--path",
        str(repo),
        "--no-version-check",
    ]
    if as_json:
        argv.append("--json")
    return runner.invoke(main, argv, env=env, catch_exceptions=False)


_CONFIG_WITH_RATIONALE = f'audit:\n  skip-rules:\n    PS-139: "{_RATIONALE}"\n'
_CONFIG_NO_RATIONALE = "audit:\n  skip-rules:\n    - PS-139\n"


# --------------------------------------------------------------------- #
# 1. A skipped rule does not fail the run                                #
# --------------------------------------------------------------------- #


def test_declared_skip_rule_does_not_fail_the_run(tmp_path):
    """A violation on a deferred rule no longer reddens audit-all."""
    # Arrange
    cfg = _CONFIG_WITH_RATIONALE
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE)
    # Assert
    assert result.exit_code == 0


def test_same_violation_fails_when_no_skip_is_declared(tmp_path):
    """Control: without the config entry the identical run is red."""
    # Arrange
    cfg = None
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE)
    # Assert
    assert result.exit_code != 0


# --------------------------------------------------------------------- #
# 2. The masked inventory is always emitted                              #
# --------------------------------------------------------------------- #


def test_masked_inventory_is_emitted(tmp_path):
    """Honouring a skip is never silent."""
    # Arrange
    cfg = _CONFIG_WITH_RATIONALE
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE)
    # Assert
    assert "MASKED INVENTORY" in result.output


def test_masked_inventory_reports_the_count(tmp_path):
    """The inventory carries how many violations were masked."""
    # Arrange
    cfg = _CONFIG_WITH_RATIONALE
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE)
    # Assert
    assert "1 violation(s) masked" in result.output


def test_masked_inventory_names_the_rule(tmp_path):
    """The inventory carries the rule ids, not just a total."""
    # Arrange
    cfg = _CONFIG_WITH_RATIONALE
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE)
    # Assert
    assert "[PS-139]" in result.output


def test_masked_inventory_prints_the_rationale(tmp_path):
    """The written rationale must reach CI logs."""
    # Arrange
    cfg = _CONFIG_WITH_RATIONALE
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE)
    # Assert
    assert _RATIONALE in result.output


# --------------------------------------------------------------------- #
# 3. A rationale-less skip entry is rejected                             #
# --------------------------------------------------------------------- #


def test_rationale_less_skip_entry_fails_the_run(tmp_path):
    """A deferral that cannot say why must not be honoured."""
    # Arrange
    cfg = _CONFIG_NO_RATIONALE
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE)
    # Assert
    assert result.exit_code == 2


def test_rationale_less_skip_entry_names_the_offender(tmp_path):
    """The rejection must name the entry so the fix is mechanical."""
    # Arrange
    cfg = _CONFIG_NO_RATIONALE
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE)
    # Assert
    assert "PS-139" in result.output


# --------------------------------------------------------------------- #
# 4. Exit code still reflects UNMASKED errors                            #
# --------------------------------------------------------------------- #


def test_undeclared_violation_still_fails_despite_declared_skips(tmp_path):
    """Declaring one deferral must not blanket-silence everything else."""
    # Arrange
    cfg = _CONFIG_WITH_RATIONALE
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_UNDECLARED_LINE)
    # Assert
    assert result.exit_code != 0


# --------------------------------------------------------------------- #
# 5. The summary states BOTH numbers                                     #
# --------------------------------------------------------------------- #


def test_summary_states_the_masked_count(tmp_path):
    """A summary reporting only '0 errors' would be a lie of omission."""
    # Arrange
    cfg = _CONFIG_WITH_RATIONALE
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE)
    # Assert
    assert "1 masked by skip-rules" in result.output


def test_summary_states_the_unmasked_error_count(tmp_path):
    """Both numbers appear, so a green run cannot hide its debt."""
    # Arrange
    cfg = _CONFIG_WITH_RATIONALE
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE)
    # Assert
    assert "0 unmasked error(s)" in result.output


def test_summary_is_emitted_for_a_single_package_run(tmp_path):
    """The summary used to appear only for multi-package runs."""
    # Arrange
    cfg = None
    # Act
    result = _run(tmp_path, config_body=cfg, failing_line=None)
    # Assert
    assert "summary: scitex-io:" in result.output


# --------------------------------------------------------------------- #
# 6. JSON mode must not be silent either                                 #
# --------------------------------------------------------------------- #


def _json_skip_rules(result):
    import json

    return json.loads(result.output)["skip_rules"]["scitex-io"]


def test_json_payload_reports_the_masked_total(tmp_path):
    """Machine consumers get the masked count, not a bare green."""
    # Arrange
    cfg = _CONFIG_WITH_RATIONALE
    # Act
    result = _run(
        tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE, as_json=True
    )
    # Assert
    assert _json_skip_rules(result)["masked_total"] == 1


def test_json_payload_carries_the_written_rationale(tmp_path):
    """The reason travels with the machine-readable payload too."""
    # Arrange
    cfg = _CONFIG_WITH_RATIONALE
    # Act
    result = _run(
        tmp_path, config_body=cfg, failing_line=_DEFERRED_LINE, as_json=True
    )
    # Assert
    assert _json_skip_rules(result)["declared"][0]["reason"] == _RATIONALE
