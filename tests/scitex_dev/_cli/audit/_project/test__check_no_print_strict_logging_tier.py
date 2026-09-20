"""PS-220 is the ecosystem-wide error-tier output discipline.

Named `test__check_no_print_strict_logging_tier.py` rather than
`test__strict_logging_tier.py`: PS-204 requires every test module to mirror a
src module, and the rule permits a trailing `_<descriptor>` on the mirror name
so one src file can host several themed test modules. The module under test is
`_check_no_print.py`, which implements the strict logging tier.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._audit import audit_project
from scitex_dev._cli.audit._project._registry import RULES


def _package(repo: Path, distribution: str, body: str, config: str = "") -> Path:
    package = distribution.replace("-", "_")
    source = repo / "src" / package
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    (source / "_runtime.py").write_text(body, encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "{distribution}"\nversion = "0.0.0"\n',
        encoding="utf-8",
    )
    cfg = repo / ".scitex" / "dev" / "config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(config or "project-type:\n  - pip\n", encoding="utf-8")
    return repo


def _audit(repo: Path, distribution: str) -> int:
    return audit_project(
        distribution,
        repo=repo,
        json_out=True,
        rules={"PS-220"},
    )


def test_ps220_is_unconditionally_error_tier() -> None:
    # Arrange
    rule = RULES["PS-220"]
    # Act
    severity = rule.severity
    # Assert
    assert severity == "E"


@pytest.mark.parametrize("distribution", ["scitex-agent-container", "scitex-writer"])
def test_human_print_fails_in_infrastructure_and_application_packages(
    tmp_path: Path, distribution: str
) -> None:
    # Arrange
    repo = _package(
        tmp_path,
        distribution,
        'def restart():\n    print("Agent restarted")\n',
    )
    # Act
    exit_code = _audit(repo, distribution)
    # Assert
    assert exit_code == 1


def test_sac_rich_restart_success_fails(tmp_path: Path) -> None:
    # Arrange
    repo = _package(
        tmp_path,
        "scitex-agent-container",
        "from rich.console import Console\n"
        "console = Console()\n"
        'def restart():\n    console.print("Agent restarted")\n',
    )
    # Act
    exit_code = _audit(repo, "scitex-agent-container")
    # Assert
    assert exit_code == 1


def test_stdlib_logger_info_fails(tmp_path: Path) -> None:
    # Arrange
    repo = _package(
        tmp_path,
        "scitex-agent-container",
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        'def restart():\n    logger.info("Agent restarted")\n',
    )
    # Act
    exit_code = _audit(repo, "scitex-agent-container")
    # Assert
    assert exit_code == 1


@pytest.mark.parametrize(
    "legacy_level",
    ["warning", "off"],
)
def test_legacy_staged_setting_cannot_weaken_gate(
    tmp_path: Path, legacy_level: str
) -> None:
    # Arrange
    repo = _package(
        tmp_path,
        "scitex-infra",
        'print("deployment complete")\n',
        config=(
            "project-type:\n  - pip\n"
            "audit:\n"
            "  enforce-logging:\n"
            f"    level: {legacy_level}\n"
            '    reason: "legacy migration setting"\n'
        ),
    )
    # Act
    exit_code = _audit(repo, "scitex-infra")
    # Assert
    assert exit_code == 1


def test_legacy_staged_setting_is_rejected_even_for_clean_source(
    tmp_path: Path,
) -> None:
    # Arrange
    repo = _package(
        tmp_path,
        "scitex-infra",
        "import scitex_logging as slogging\nlog = slogging.getLogger(__name__)\n",
        config=("project-type:\n  - pip\naudit:\n  enforce-logging: warning\n"),
    )
    # Act
    exit_code = _audit(repo, "scitex-infra")
    # Assert
    assert exit_code == 1


def test_json_stdout_emitter_passes(tmp_path: Path) -> None:
    # Arrange
    repo = _package(
        tmp_path,
        "scitex-protocol",
        "import json\n"
        "def emit_json(payload):\n"
        "    print(json.dumps(payload, sort_keys=True))\n",
    )
    # Act
    exit_code = _audit(repo, "scitex-protocol")
    # Assert
    assert exit_code == 0


def test_caller_owned_rendering_stream_passes(tmp_path: Path) -> None:
    # Arrange
    repo = _package(
        tmp_path,
        "scitex-writer",
        "def render_report(report, stream):\n    print(report.render(), file=stream)\n",
    )
    # Act
    exit_code = _audit(repo, "scitex-writer")
    # Assert
    assert exit_code == 0


def test_explicit_content_api_passes(tmp_path: Path) -> None:
    # Arrange
    repo = _package(
        tmp_path,
        "scitex-writer",
        "def render_content(content):\n    print(content)\n",
    )
    # Act
    exit_code = _audit(repo, "scitex-writer")
    # Assert
    assert exit_code == 0


def test_scitex_logging_passes(tmp_path: Path) -> None:
    # Arrange
    repo = _package(
        tmp_path,
        "scitex-infra",
        "import scitex_logging as slogging\n"
        "logger = slogging.getLogger(__name__)\n"
        'def deploy():\n    logger.success("deployment complete")\n',
    )
    # Act
    exit_code = _audit(repo, "scitex-infra")
    # Assert
    assert exit_code == 0
