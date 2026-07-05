"""Tests for raw-external-library IMPORT severity promotion under research mode.

Operator directive 2026-06-30 (mirrors PR #264's figure/plot promotion):
research projects must use the stx umbrella (`stx.plt` / `stx.stats` /
`stx.io`) instead of importing the raw third-party library directly. The
relevant IMPORT rules already FIRE in research mode but only as WARNINGS;
these tests pin the new SEVERITY wiring that promotes them to ERROR so the
post-edit hook (run_lint.sh, exit 2) BLOCKS the raw import.

Promoted set (per_rule_severity, NOT a category override — see config.py):
- STX-I001  `import matplotlib.pyplot` → `stx.plt`
- STX-I002  `import scipy.stats`        → `stx.stats`
- STX-I009  `import seaborn`            → `stx.plt` (figrecipe wrappers)

Deliberately NOT promoted (share the same "import" category but are a
DIFFERENT concern — these stay at their default severity in research):
- STX-I003  pickle file I/O          (warn-only)
- STX-I006  `import random`          (info; injection hygiene)
- STX-I007  `import logging`         (warn-only; injection hygiene)
- STX-I008  cross-package private-submodule import (warn-only)

This is WHY the mechanism is per_rule_severity and not a category bump:
promoting the whole "import" category would over-promote I003/I006/I007/I008.

Real fixtures + the real checker — no mocks. STX-I001/I002/I009 fire
regardless of figrecipe (they live in scitex-dev's own _import_hygiene
rules, gated only on `requires="scitex"`), so these tests need scitex
importable but NOT figrecipe.
"""

from __future__ import annotations

import importlib.util

import pytest

from scitex_dev.linter.checker import lint_source
from scitex_dev.linter.config import LinterConfig, load_config

# The STX-I0xx import rules carry ``requires="scitex"`` and are SILENTLY
# SKIPPED if scitex is not importable in the interpreter. Gate so the suite
# does not silently pass on an env where the rule never fires.
_HAS_SCITEX = importlib.util.find_spec("scitex") is not None
requires_scitex = pytest.mark.skipif(
    not _HAS_SCITEX, reason="scitex umbrella not installed in this interpreter"
)


# Research-mode config as load_config builds it for a research project:
# the figure-family category floor PLUS the raw-extlib import per-rule pins.
def _research_config(**extra):
    return LinterConfig(
        category_severity_override={
            "io": "error",
            "path": "error",
            "figure": "error",
            "plot": "error",
        },
        per_rule_severity={
            "STX-I001": "error",
            "STX-I002": "error",
            "STX-I009": "error",
        },
        **extra,
    )


def _sev_of(issues, rule_id):
    """Return the severity emitted for *rule_id*, or None if not present."""
    for i in issues:
        if i.rule.id == rule_id:
            return i.rule.severity
    return None


_I001_SRC = "import matplotlib.pyplot as plt\n"
_I002_SRC = "from scipy import stats\n"
_I009_SRC = "import seaborn as sns\n"
_I008_SRC = "from scitex_io._save import save\n"
_I003_SRC = "import pickle\n"


# ---------------------------------------------------------------------- #
# (a) research config (scalar-equivalent) → I001/I002/I009 promote to error
# ---------------------------------------------------------------------- #


@requires_scitex
class TestImportRulesPromotedInResearch:
    def test_i001_matplotlib_promoted_to_error(self):
        # Arrange
        cfg = _research_config()
        # Act
        issues = lint_source(_I001_SRC, "mod.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-I001") == "error", (
            f"I001 must promote to error in research; "
            f"got {[(i.rule.id, i.rule.severity) for i in issues]}"
        )

    def test_i002_scipy_stats_promoted_to_error(self):
        # Arrange
        cfg = _research_config()
        # Act
        issues = lint_source(_I002_SRC, "mod.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-I002") == "error"

    def test_i009_seaborn_promoted_to_error(self):
        # Arrange
        cfg = _research_config()
        # Act
        issues = lint_source(_I009_SRC, "mod.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-I009") == "error"


# ---------------------------------------------------------------------- #
# (c) NON-research project → I001/I002/I009 stay at their default warning
# ---------------------------------------------------------------------- #


@requires_scitex
class TestImportRulesStayWarningOutsideResearch:
    def test_i001_default_warning(self):
        # Arrange
        cfg = LinterConfig()  # pip/default: no override, no per-rule pin
        # Act
        issues = lint_source(_I001_SRC, "mod.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-I001") == "warning"

    def test_i002_default_warning(self):
        # Arrange
        cfg = LinterConfig()
        # Act
        issues = lint_source(_I002_SRC, "mod.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-I002") == "warning"

    def test_i009_default_warning(self):
        # Arrange
        cfg = LinterConfig()
        # Act
        issues = lint_source(_I009_SRC, "mod.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-I009") == "warning"


# ---------------------------------------------------------------------- #
# (d) escape hatch: `# stx-allow: STX-I001` → fully suppressed in research
# ---------------------------------------------------------------------- #


@requires_scitex
class TestEscapeHatchPreserved:
    def test_stx_allow_fully_suppresses_i001_in_research(self):
        # Arrange
        cfg = _research_config()
        src = "import matplotlib.pyplot as plt  # stx-allow: STX-I001\n"
        # Act
        issues = lint_source(src, "mod.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-I001") is None, (
            f"# stx-allow must fully suppress I001 even in research; "
            f"got {[(i.rule.id, i.rule.severity) for i in issues]}"
        )

    def test_stx_allow_fully_suppresses_i009_in_research(self):
        # Arrange
        cfg = _research_config()
        src = "import seaborn as sns  # stx-allow: STX-I009\n"
        # Act
        issues = lint_source(src, "mod.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-I009") is None


# ---------------------------------------------------------------------- #
# (e) NOT-promoted rules: I008 (private import) / I003 (pickle) stay default
#     — proves we did NOT over-promote the whole "import" category.
# ---------------------------------------------------------------------- #


@requires_scitex
class TestUnpromotedImportRulesUnchangedInResearch:
    def test_i008_private_import_stays_warning(self):
        # Arrange — I008 shares category "import" with I001/I002/I009 but is
        # a DIFFERENT concern (cross-pkg private import); own_package is
        # inferred from path, so use a peer-importing source file.
        cfg = _research_config()
        # Act
        issues = lint_source(_I008_SRC, "src/scitex_gen/mod.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-I008") == "warning", (
            f"I008 must stay warning in research (not over-promoted); "
            f"got {[(i.rule.id, i.rule.severity) for i in issues]}"
        )

    def test_i003_pickle_stays_warning(self):
        # Arrange
        cfg = _research_config()
        # Act
        issues = lint_source(_I003_SRC, "mod.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-I003") == "warning"


# ---------------------------------------------------------------------- #
# (a)/(b) End-to-end via load_config: scalar + block-list project-type forms
# ---------------------------------------------------------------------- #


@requires_scitex
class TestResearchYamlFormsPromoteImportRules:
    def _run(self, tmp_path, yaml_body, src):
        (tmp_path / ".scitex" / "dev").mkdir(parents=True)
        (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(yaml_body)
        cfg = load_config(start_path=str(tmp_path))
        return lint_source(src, str(tmp_path / "mod.py"), cfg)

    def test_scalar_form_promotes_i001(self, tmp_path):
        # Arrange
        yaml_body = "project-type: research\n"
        # Act
        issues = self._run(tmp_path, yaml_body, _I001_SRC)
        # Assert
        assert _sev_of(issues, "STX-I001") == "error"

    def test_scalar_form_promotes_i009(self, tmp_path):
        # Arrange
        yaml_body = "project-type: research\n"
        # Act
        issues = self._run(tmp_path, yaml_body, _I009_SRC)
        # Assert
        assert _sev_of(issues, "STX-I009") == "error"

    def test_block_list_form_promotes_i001(self, tmp_path):
        # Arrange
        yaml_body = "project-type:\n  - research\n"
        # Act
        issues = self._run(tmp_path, yaml_body, _I001_SRC)
        # Assert
        assert _sev_of(issues, "STX-I001") == "error"

    def test_block_list_form_promotes_i002(self, tmp_path):
        # Arrange
        yaml_body = "project-type:\n  - research\n"
        # Act
        issues = self._run(tmp_path, yaml_body, _I002_SRC)
        # Assert
        assert _sev_of(issues, "STX-I002") == "error"

    def test_non_research_yaml_keeps_i001_warning(self, tmp_path):
        # Arrange
        yaml_body = "project-type: pip\n"
        # Act
        issues = self._run(tmp_path, yaml_body, _I001_SRC)
        # Assert
        assert _sev_of(issues, "STX-I001") == "warning"

    def test_research_yaml_does_not_promote_i008(self, tmp_path):
        # Arrange — end-to-end proof the unrelated private-import rule stays
        # warning; own_package is inferred from the src/scitex_gen path.
        (tmp_path / ".scitex" / "dev").mkdir(parents=True)
        (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(
            "project-type: research\n"
        )
        cfg = load_config(start_path=str(tmp_path))
        srcdir = tmp_path / "src" / "scitex_gen"
        srcdir.mkdir(parents=True)
        modfile = srcdir / "mod.py"
        modfile.write_text(_I008_SRC)
        # Act
        issues = lint_source(_I008_SRC, str(modfile), cfg)
        # Assert
        assert _sev_of(issues, "STX-I008") == "warning"

    def test_operator_per_rule_pin_wins_over_research_promotion(self, tmp_path):
        # Arrange — an explicit per-rule pin must survive the research
        # promotion (per_rule_severity merge keeps existing user pins).
        (tmp_path / ".scitex" / "dev").mkdir(parents=True)
        (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(
            "project-type: research\n"
        )
        cfg = load_config(start_path=str(tmp_path))
        cfg.per_rule_severity = {**cfg.per_rule_severity, "STX-I001": "info"}
        # Act
        issues = lint_source(_I001_SRC, str(tmp_path / "mod.py"), cfg)
        # Assert
        assert _sev_of(issues, "STX-I001") == "info"


# EOF
