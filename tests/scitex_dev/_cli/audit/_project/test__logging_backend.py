"""Owner backend proof and adversarial PS-220 controls; no source imports."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_no_print import check_ps220_no_print


@dataclass
class Finding:
    rule: str
    where: str
    detail: str


_INIT = (
    "import logging as _logging\n"
    "from ._logger import setup_logger_class as _setup_logger_class\n"
    "getLogger = _logging.getLogger\n"
    "raise RuntimeError('audit must not import the source')\n"
)
_LOGGER = (
    "import logging\n"
    "class SciTeXLogger(logging.Logger):\n    pass\n"
    "def setup_logger_class():\n"
    "    logging.setLoggerClass(SciTeXLogger)\n"
    "    root = logging.getLogger()\n"
    "    root.__class__ = SciTeXLogger\n"
)


def _source(repo: Path, relative: str, body: str) -> Path:
    path = repo / "src" / "scitex_logging" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _owner(repo: Path) -> None:
    (repo / "pyproject.toml").write_text('[project]\nname = "scitex-logging"\n')
    _source(repo, "__init__.py", _INIT)
    _source(repo, "_logger.py", _LOGGER)


def _findings(repo: Path) -> list[Finding]:
    out = []
    check_ps220_no_print(repo, Finding, out)
    return out


@pytest.mark.parametrize(
    ("filename", "body"),
    [
        ("_logger.py", _LOGGER),
        ("_config.py", "import logging\ndef set_level(level):\n"
         "    logging.getLogger().setLevel(level)\n"
         "    for handler in logging.getLogger().handlers:\n"
         "        handler.setLevel(level)\n"),
        ("_config.py", "import logging\ndef get_level():\n"
         "    return _GLOBAL_LEVEL or logging.getLogger().level\n"),
        ("_config.py", "import logging\ndef configure():\n"
         "    root_logger = logging.getLogger()\n"),
        ("_config.py", "import logging\ndef get_log_path():\n"
         "    for handler in logging.getLogger().handlers:\n"
         "        if hasattr(handler, 'baseFilename'):\n"
         "            return handler.baseFilename\n"),
        ("_context.py", "import logging as _logging\ndef log_to_file():\n"
         "    root_logger = _logging.getLogger()\n"),
        ("_console.py", "import logging\ndef getConsole(name=None):\n"
         "    console = logging.getLogger(name or DEFAULT_CONSOLE_NAME)\n"),
        ("_print_capture.py", "import logging\nclass PrintCapture:\n"
         "    def __init__(self, logger_name):\n"
         "        self.logger = logging.getLogger(logger_name)\n"),
    ],
)
def test_canonical_backend_operations_pass_without_importing_source(tmp_path, filename, body):
    # Arrange
    _owner(tmp_path)
    _source(tmp_path, filename, body)
    # Act
    findings = _findings(tmp_path)
    # Assert
    assert findings == []


@pytest.mark.parametrize("metadata", ["[project]\nname='scitex-other'\n", "invalid TOML"])
def test_copied_package_path_cannot_claim_backend_ownership(tmp_path, metadata):
    # Arrange
    _owner(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(metadata)
    # Act
    findings = _findings(tmp_path)
    # Assert
    assert len(findings) == 1 and "stdlib logging.getLogger" in findings[0].detail


def test_missing_distribution_metadata_cannot_claim_backend_ownership(tmp_path):
    # Arrange
    _owner(tmp_path)
    (tmp_path / "pyproject.toml").unlink()
    # Act
    findings = _findings(tmp_path)
    # Assert
    assert len(findings) == 1 and "stdlib logging.getLogger" in findings[0].detail


@pytest.mark.parametrize(
    ("filename", "body"),
    [("__init__.py", ""), ("_logger.py", "import logging\ndef setup_logger_class():\n"
      "    root = logging.getLogger()\n")],
)
def test_distribution_name_and_paths_without_real_backend_wiring_fail(tmp_path, filename, body):
    # Arrange
    _owner(tmp_path)
    _source(tmp_path, filename, body)
    # Act
    findings = _findings(tmp_path)
    # Assert
    assert len(findings) == 1


@pytest.mark.parametrize("filename", ["_diagnostics.py", "nested/_config.py", "_config.py"])
def test_ordinary_logger_acquisition_still_fails_in_owner_source(tmp_path, filename):
    # Arrange
    _owner(tmp_path)
    _source(tmp_path, filename, "import logging\ndef diagnose():\n"
            "    logger = logging.getLogger(__name__)\n    logger.info('status')\n")
    # Act
    findings = _findings(tmp_path)
    # Assert
    assert len(findings) == 1 and filename in findings[0].where


@pytest.mark.parametrize("extra", [
    "    logging.getLogger('diagnostic').info('status')\n",
    "    from logging import getLogger as acquire\n    acquire(__name__).info('status')\n",
    "    print('status')\n",
    "    from rich.console import Console\n    console = Console()\n    console.print('status')\n",
])
def test_extra_diagnostics_in_canonical_backend_function_still_fail(tmp_path, extra):
    # Arrange
    _owner(tmp_path)
    _source(tmp_path, "_logger.py", _LOGGER + extra)
    # Act
    findings = _findings(tmp_path)
    # Assert
    assert len(findings) == 1 and findings[0].rule == "PS-220"


def test_nested_scope_with_backend_function_name_is_not_an_allowance(tmp_path):
    # Arrange
    _owner(tmp_path)
    _source(tmp_path, "_config.py", "import logging\ndef diagnose():\n"
            "    def configure():\n        root_logger = logging.getLogger()\n")
    # Act
    findings = _findings(tmp_path)
    # Assert
    assert len(findings) == 1


def test_changed_backend_call_shape_fails_closed(tmp_path):
    # Arrange
    _owner(tmp_path)
    _source(tmp_path, "_config.py", "import logging\ndef configure():\n"
            "    root_logger = logging.getLogger('caller-diagnostic')\n")
    # Act
    findings = _findings(tmp_path)
    # Assert
    assert len(findings) == 1


def test_symlinked_foreign_module_cannot_gain_owner_allowance(tmp_path):
    # Arrange
    _owner(tmp_path)
    foreign = tmp_path / "foreign.py"
    foreign.write_text("import logging\ndef configure():\n"
                       "    root_logger = logging.getLogger()\n")
    path = tmp_path / "src" / "scitex_logging" / "_config.py"
    path.symlink_to(foreign)
    # Act
    findings = _findings(tmp_path)
    # Assert
    assert len(findings) == 1


def test_diagnostics_in_a_nonowner_same_backend_layout_all_fire(tmp_path):
    # Arrange
    _owner(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='scitex-client'\n")
    _source(tmp_path, "_config.py", "import logging\nfrom rich.console import Console\n"
            "def configure():\n    root_logger = logging.getLogger()\n"
            "    print('status')\n    console = Console()\n    console.print('status')\n")
    # Act
    findings = _findings(tmp_path)
    # Assert
    assert len(findings) == 4 and {item.rule for item in findings} == {"PS-220"}
