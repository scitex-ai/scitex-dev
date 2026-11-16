"""Tests for the plugin-SPI rule scope gate and required capabilities.

Real objects only: real ``Rule`` / ``Issue`` values, a real checker class fed
through ``lint_source``'s documented ``plugins`` seam, real tmp projects for
``lint_file``.
"""

from __future__ import annotations

from scitex_dev.linter import _plugin_loader
from scitex_dev.linter._dispatch import lint_file
from scitex_dev.linter._research_scope import (
    apply_scopes,
    check_required_capabilities,
    is_research_script,
)
from scitex_dev.linter.checker import lint_source
from scitex_dev.linter.config import LinterConfig
from scitex_dev.linter.spi import SCOPE_RESEARCH_SCRIPT, Issue, Rule

_SCOPED = Rule(
    "TEST-SCOPED1",
    "warning",
    "io",
    "scoped test rule",
    "fix it",
    scope=SCOPE_RESEARCH_SCRIPT,
)
_ANY = Rule("TEST-ANY1", "warning", "io", "unscoped test rule", "fix it")


class _EmitBothChecker:
    """Plugin-style checker: emits one scoped and one unscoped finding."""

    category = "io"

    def __init__(self, lines, config):
        self.issues = []

    def visit(self, tree):
        self.issues.append(Issue(_SCOPED, 1, 0, ""))
        self.issues.append(Issue(_ANY, 1, 0, ""))


_SESSION_SRC = (
    "import scitex as stx\n"
    "\n"
    "\n"
    "@stx.session\n"
    "def main(CONFIG=stx.session.INJECTED, COLORS=stx.session.INJECTED,\n"
    "         logger=stx.session.INJECTED, plt=stx.session.INJECTED,\n"
    "         rngg=stx.session.INJECTED):\n"
    "    return 0\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)


def _error(fn, *args):
    """Message of the LinterPluginError *fn* raises ('' when it returns)."""
    try:
        fn(*args)
    except _plugin_loader.LinterPluginError as exc:
        return str(exc)
    return ""


def _test_ids(src, filepath):
    issues = lint_source(
        src,
        filepath=filepath,
        config=LinterConfig(),
        plugins={"checkers": [_EmitBothChecker]},
    )
    return sorted(i.rule.id for i in issues if i.rule.id.startswith("TEST-"))


# -- is_research_script ------------------------------------------------------


def test_session_decorated_module_is_research_script():
    # Arrange
    cfg = LinterConfig()
    # Act
    verdict = is_research_script("examples/run.py", cfg, has_entry_decorator=True)
    # Assert
    assert verdict is True


def test_research_project_scripts_dir_is_research_script():
    # Arrange
    cfg = LinterConfig(project_types=["research"])
    # Act
    verdict = is_research_script("scripts/pac/calc.py", cfg, has_entry_decorator=False)
    # Assert
    assert verdict is True


def test_non_research_scripts_dir_is_not_research_script():
    # Arrange
    cfg = LinterConfig()
    # Act
    verdict = is_research_script(
        "scripts/release/bump.py", cfg, has_entry_decorator=False
    )
    # Assert
    assert verdict is False


def test_session_decorated_test_file_is_not_research_script():
    # Arrange
    cfg = LinterConfig(project_types=["research"])
    # Act
    verdict = is_research_script("tests/test_run.py", cfg, has_entry_decorator=True)
    # Assert
    assert verdict is False


def test_research_library_module_is_not_research_script():
    # Arrange
    cfg = LinterConfig(project_types=["research"])
    # Act
    verdict = is_research_script("src/pkg/_cache.py", cfg, has_entry_decorator=False)
    # Assert
    assert verdict is False


# -- apply_scopes ------------------------------------------------------------


def test_apply_scopes_drops_scoped_finding_outside_research_script():
    # Arrange
    issues = [Issue(_SCOPED, 1, 0, ""), Issue(_ANY, 2, 0, "")]
    # Act
    kept = apply_scopes(issues, research_script=False)
    # Assert
    assert [i.rule.id for i in kept] == ["TEST-ANY1"]


def test_apply_scopes_keeps_everything_in_research_script():
    # Arrange
    issues = [Issue(_SCOPED, 1, 0, ""), Issue(_ANY, 2, 0, "")]
    # Act
    kept = apply_scopes(issues, research_script=True)
    # Assert
    assert len(kept) == 2


# -- engine applies the scope to plugin checkers ------------------------------


def test_engine_drops_plugin_scoped_finding_in_library_module():
    # Arrange
    src = "def f():\n    return 1\n"
    # Act
    ids = _test_ids(src, "src/pkg/mod.py")
    # Assert
    assert ids == ["TEST-ANY1"]


def test_engine_keeps_plugin_scoped_finding_in_session_script():
    # Arrange — the decorator sits BELOW where findings were emitted; the
    # verdict is taken after the whole module is visited.
    # Act
    ids = _test_ids(_SESSION_SRC, "examples/run.py")
    # Assert
    assert ids == ["TEST-ANY1", "TEST-SCOPED1"]


# -- plugin loader validates the new SPI keys --------------------------------


def test_loader_rejects_unknown_rule_scope():
    # Arrange
    bad = Rule("TEST-BAD1", "warning", "io", "m", "s", scope="everywhere")
    # Act
    msg = _error(_plugin_loader._validate_payload, {"rules": [bad]}, "test")
    # Assert
    assert "invalid Rule" in msg


def test_loader_rejects_non_list_capabilities():
    # Arrange
    payload = {"rules": [], "capabilities": "raw-io"}
    # Act
    msg = _error(_plugin_loader._validate_payload, payload, "test")
    # Assert
    assert "capabilities must be a list" in msg


# -- required capabilities fail loud -----------------------------------------


def test_research_project_without_raw_io_capability_raises():
    # Arrange
    cfg = LinterConfig(project_types=["research"])
    # Act
    msg = _error(check_required_capabilities, cfg, {})
    # Assert
    assert "scitex-io>=0.5.0" in msg


def test_research_project_with_raw_io_capability_passes():
    # Arrange
    cfg = LinterConfig(project_types=["research"])
    # Act
    result = check_required_capabilities(cfg, {"raw-io": "io (scitex_io)"})
    # Assert
    assert result is None


def test_non_research_project_needs_no_capability():
    # Arrange
    cfg = LinterConfig()
    # Act
    result = check_required_capabilities(cfg, {})
    # Assert
    assert result is None


def test_lint_file_checks_installed_capabilities_for_research_project(tmp_path):
    # Arrange — a real research project; the verdict follows the INSTALLED
    # providers: clean lint when one declares raw-io, loud error otherwise.
    (tmp_path / ".scitex" / "dev").mkdir(parents=True)
    (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(
        "project-type: research\n"
    )
    script = tmp_path / "scripts" / "pac" / "calc_pac.py"
    script.parent.mkdir(parents=True)
    script.write_text("x = 1\n")
    declared = "raw-io" in _plugin_loader.load_plugins().get("capabilities", {})
    # Act
    try:
        lint_file(str(script))
        outcome = "linted"
    except _plugin_loader.LinterPluginError:
        outcome = "refused"
    # Assert
    assert outcome == ("linted" if declared else "refused")
