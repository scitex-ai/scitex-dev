"""Tests for gate config resolution (.scitex/dev/config.yaml `gate:` section)."""

from __future__ import annotations

from pathlib import Path

from scitex_dev.gate import load_gate_config


def _write_cfg(root: Path, body: str) -> Path:
    cfg = root / ".scitex" / "dev"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(body, encoding="utf-8")
    return root


def test_missing_config_is_warn_default():
    # Arrange — a bare dir with no .scitex/dev/config.yaml.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        # Act
        cfg = load_gate_config(td)
        # Assert
        assert cfg.enforce == frozenset() and cfg.disable == frozenset()


def test_enforce_list_is_parsed():
    # Arrange
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        _write_cfg(
            Path(td),
            "gate:\n  enforce:\n    - clew-source-reachability\n    - dataset-submission-format\n",
        )
        # Act
        cfg = load_gate_config(td)
        # Assert
        assert cfg.is_enforced("clew-source-reachability") is True


def test_disable_list_is_parsed():
    # Arrange
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), "gate:\n  disable:\n    - some-check\n")
        # Act
        cfg = load_gate_config(td)
        # Assert
        assert cfg.is_disabled("some-check") is True


def test_config_resolves_walking_up_from_subdir():
    # Arrange — config at root, workdir a nested capsule dir.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), "gate:\n  enforce: [clew-source-reachability]\n")
        capsule = Path(td) / "runs" / "capsule-007"
        capsule.mkdir(parents=True)
        # Act
        cfg = load_gate_config(capsule)
        # Assert
        assert cfg.is_enforced("clew-source-reachability") is True


def test_no_gate_section_is_warn_default():
    # Arrange — a config that declares project-type but no gate section.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), "project-type: research\n")
        # Act
        cfg = load_gate_config(td)
        # Assert
        assert cfg.enforce == frozenset()


def test_scalar_enforce_value_is_accepted():
    # Arrange — a single string instead of a list.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), "gate:\n  enforce: clew-source-reachability\n")
        # Act
        cfg = load_gate_config(td)
        # Assert
        assert cfg.is_enforced("clew-source-reachability") is True
