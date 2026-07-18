"""Tests for figure-family severity promotion under ``project-type: research``.

v1 (operator directive 2026-06-28): the linter already DETECTS figure-bypass
patterns (figrecipe owns detection); these tests pin the new SEVERITY wiring
that promotes the EXISTING figure-family rules to ERROR in research projects
so the post-edit hook (run_lint.sh, exit 2) BLOCKS figure-bypass code.

v1 promoted set (verified against figrecipe ``_linter_plugin.py``):
- category ``figure``: STX-FM001..FM011 + STX-FIG001
- category ``plot``:   STX-P001..P009

Emit paths feeding one combined issue list:
- ``FMChecker._add``                         → FM001-FM009  (scitex-dev)
- figrecipe ``FigureMethodChecker._emit``    → FM010/FM011  (read-only)
- figrecipe ``AxisAlignmentChecker._emit``   → FIG001       (read-only)
- figrecipe ``StyleKwargChecker._emit``      → P006-P009    (read-only)
- ``SciTeXChecker._add`` (axes_hints/calls)  → P001-P005

The figrecipe checkers honour only ``per_rule_severity`` and ignore the
category override, so ``SciTeXChecker.get_issues`` applies
``promote_category_severity`` as a central floor over the combined list.
These tests use REAL fixtures + the REAL figrecipe plugin — no mocks.
"""

from __future__ import annotations

import importlib.util

import pytest

from scitex_dev.linter._rules._base import Rule
from scitex_dev.linter._severity_promotion import promote_category_severity
from scitex_dev.linter.checker import Issue, lint_source
from scitex_dev.linter.config import LinterConfig, load_config

# figrecipe ships the figure-family DETECTION (FM010/FM011/FIG001/P006-P009).
# The end-to-end tests need its plugin installed; gate them so the unit-level
# promotion tests still run in a figrecipe-less env.
_HAS_FIGRECIPE = importlib.util.find_spec("figrecipe") is not None
requires_figrecipe = pytest.mark.skipif(
    not _HAS_FIGRECIPE, reason="figrecipe plugin not installed in this interpreter"
)


def _rule_registered(rule_id: str) -> bool:
    """Return True iff *rule_id* is in the loaded linter rule set.

    figrecipe-IMPORTABLE is not the same as figrecipe-PROVIDES-this-rule: a
    baked CI/SIF image can carry an OLDER figrecipe whose plugin predates a
    given rule (e.g. STX-FM010 / STX-P006). figrecipe then imports fine — so
    ``@requires_figrecipe`` passes — yet the rule never registers and the
    promotion never fires, turning a version-skew into a hard test FAILURE.
    The plugin loader merges every plugin's rules into a dict keyed by rule
    id, so membership there is the precise "is this rule available?" check.
    """
    from scitex_dev.linter._plugin_loader import load_plugins

    return rule_id in load_plugins().get("rules", {})


def requires_rule(rule_id: str):
    """skipif guard for a plugin-PROVIDED rule that may be absent on old figrecipe."""
    return pytest.mark.skipif(
        not _rule_registered(rule_id),
        reason=(
            f"{rule_id} not registered — installed figrecipe predates this rule"
        ),
    )


def _skip_if_not_emitted(issues, rule_id):
    """Skip when *rule_id* did not actually fire on the fixture (detection skew).

    ``@requires_rule`` only proves the rule is REGISTERED in the loaded plugin
    set — not that this figrecipe's checker EMITS it for a given fixture. A
    baked/reused CI SIF can layer a figrecipe whose detector maps the same
    pattern to a different rule id (e.g. STX-P002 instead of STX-P006), so the
    rule registers (guard passes) yet never fires here. That is a
    figrecipe-version skew, NOT a scitex-dev promotion regression — so we SKIP,
    not fail (a hard fail here blocked the v0.23.0 release, 2026-07-01). A real
    regression — the rule fires but stays ``warning`` — still fails the assert
    below, because ``_sev_of`` returns ``warning`` (not ``None``) in that case.
    """
    if not any(i.rule.id == rule_id for i in issues):
        pytest.skip(
            f"{rule_id} not emitted by the installed figrecipe on this fixture "
            f"(detection skew — got {sorted({i.rule.id for i in issues})}); "
            f"promotion mechanism is untestable without it firing"
        )


def _research_config(**extra):
    """A synthetic research-mode config (FM enabled + full v1 category floor)."""
    return LinterConfig(
        enable=["FM"],
        category_severity_override={
            "io": "error",
            "path": "error",
            "figure": "error",
            "plot": "error",
        },
        **extra,
    )


def _sev_of(issues, rule_id):
    """Return the severity emitted for *rule_id*, or None if not present."""
    for i in issues:
        if i.rule.id == rule_id:
            return i.rule.severity
    return None


def _mk_issue(rule_id, category, severity):
    """Build a synthetic Issue carrying a Rule with the given category/severity."""
    rule = Rule(
        id=rule_id, severity=severity, category=category, message="m", suggestion="s"
    )
    return Issue(rule=rule, line=1, col=0, source_line="x")


_FM001_SRC = "import matplotlib.pyplot as plt\nfig, ax = plt.subplots(figsize=(4, 3))\n"
_CLEAN_SRC = (
    "import figrecipe as fr\n"
    "fig, ax = fr.subplots(axes_width_mm=40, axes_height_mm=28)\n"
)


# ---------------------------------------------------------------------- #
# Unit: promote_category_severity (figrecipe-independent)                #
# ---------------------------------------------------------------------- #


class TestPromoteCategorySeverityUnit:
    """The central floor pass: category override applied, per-rule wins."""

    def test_figure_issue_promoted_to_error(self):
        # Arrange — a figure-category issue emitted at its default warning.
        issues = [_mk_issue("STX-FM010", "figure", "warning")]
        # Act
        out = promote_category_severity(issues, _research_config())
        # Assert
        assert _sev_of(out, "STX-FM010") == "error"

    def test_plot_issue_promoted_to_error(self):
        # Arrange — a plot-category issue emitted at its default warning.
        issues = [_mk_issue("STX-P006", "plot", "warning")]
        # Act
        out = promote_category_severity(issues, _research_config())
        # Assert
        assert _sev_of(out, "STX-P006") == "error"

    def test_per_rule_pin_wins_over_category_floor(self):
        # Arrange — operator pinned FM010 to warning; floor must not touch it.
        cfg = _research_config(per_rule_severity={"STX-FM010": "warning"})
        issues = [_mk_issue("STX-FM010", "figure", "warning")]
        # Act
        out = promote_category_severity(issues, cfg)
        # Assert
        assert _sev_of(out, "STX-FM010") == "warning"

    def test_no_override_leaves_severity_unchanged(self):
        # Arrange — non-research config has an empty override map.
        cfg = LinterConfig()
        issues = [_mk_issue("STX-FM010", "figure", "warning")]
        # Act
        out = promote_category_severity(issues, cfg)
        # Assert
        assert _sev_of(out, "STX-FM010") == "warning"

    def test_unrelated_category_not_promoted(self):
        # Arrange — override targets figure only; a structure issue is present.
        cfg = LinterConfig(category_severity_override={"figure": "error"})
        issues = [_mk_issue("STX-S999", "structure", "warning")]
        # Act
        out = promote_category_severity(issues, cfg)
        # Assert
        assert _sev_of(out, "STX-S999") == "warning"


# ---------------------------------------------------------------------- #
# End-to-end: real figrecipe plugin, real source fixtures                #
# ---------------------------------------------------------------------- #


@requires_figrecipe
class TestFM001PromotionEndToEnd:
    """(a)/(c)/(d)/(e) — FM001 via the FMChecker path, end to end."""

    def test_research_config_makes_fm001_an_error(self):
        # Arrange — research config; FM001 is a clear figure violation.
        cfg = _research_config()
        # Act
        issues = lint_source(_FM001_SRC, "fig.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-FM001") == "error", (
            f"FM001 must promote to error; "
            f"got {[(i.rule.id, i.rule.severity) for i in issues]}"
        )

    def test_non_research_config_keeps_fm001_warning(self):
        # Arrange — non-research config (no category override).
        cfg = LinterConfig(enable=["FM"])
        # Act
        issues = lint_source(_FM001_SRC, "fig.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-FM001") == "warning"

    def test_clean_figrecipe_code_has_no_figure_finding(self):
        # Arrange — idiomatic figrecipe code under a research config.
        cfg = _research_config()
        # Act
        issues = lint_source(_CLEAN_SRC, "fig.py", cfg)
        # Assert
        figure_ids = [
            i.rule.id for i in issues if i.rule.category in ("figure", "plot")
        ]
        assert figure_ids == [], (
            f"clean code must not flag figure rules; got {figure_ids}"
        )

    def test_per_rule_pin_keeps_fm001_warning_in_research(self):
        # Arrange — research config but FM001 pinned to warning per-rule.
        cfg = _research_config(per_rule_severity={"STX-FM001": "warning"})
        # Act
        issues = lint_source(_FM001_SRC, "fig.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-FM001") == "warning"

    def test_bare_stx_allow_fully_suppresses_fm001_in_research(self):
        # Arrange — research config; the violating line carries the bare
        # ``# stx-allow`` opt-out. Regression (figrecipe v1 ask): suppression
        # must emit NOTHING even under research mode — the promotion floor only
        # flips the severity of an ALREADY-emitted finding, it must never
        # resurrect a line the author explicitly suppressed.
        cfg = _research_config()
        src = (
            "import matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots(figsize=(4, 3))  # stx-allow: STX-FM001\n"
        )
        # Act
        issues = lint_source(src, "fig.py", cfg)
        # Assert
        assert _sev_of(issues, "STX-FM001") is None, (
            f"bare # stx-allow must fully suppress FM001 even in research; "
            f"got {[(i.rule.id, i.rule.severity) for i in issues]}"
        )


@requires_figrecipe
class TestPluginPathPromotionEndToEnd:
    """Plugin-path rules (P006-P009 / FM010/FM011) also promote."""

    @requires_rule("STX-P006")
    def test_p006_style_kwarg_promoted_to_error(self):
        # Arrange — P006 fires from figrecipe's StyleKwargChecker (plugin path).
        cfg = _research_config()
        src = "import matplotlib.pyplot as plt\nax.scatter(x, y, s=5)\n"
        # Act
        issues = lint_source(src, "fig.py", cfg)
        _skip_if_not_emitted(issues, "STX-P006")
        # Assert
        assert _sev_of(issues, "STX-P006") == "error", (
            f"P006 (plugin path) must promote to error; "
            f"got {[(i.rule.id, i.rule.severity) for i in issues]}"
        )

    @requires_rule("STX-FM010")
    def test_fm010_figure_method_promoted_to_error(self):
        # Arrange — FM010 fires from figrecipe's FigureMethodChecker (plugin).
        cfg = _research_config()
        src = "ax.set_xlabel('X')\n"
        # Act
        issues = lint_source(src, "fig.py", cfg)
        _skip_if_not_emitted(issues, "STX-FM010")
        # Assert
        assert _sev_of(issues, "STX-FM010") == "error"


# ---------------------------------------------------------------------- #
# End-to-end via load_config: scalar + block-list project-type forms     #
# ---------------------------------------------------------------------- #


@requires_figrecipe
class TestResearchConfigYamlForms:
    """(a)/(b) — both YAML shapes of project-type promote FM001 to error."""

    def _run(self, tmp_path, yaml_body):
        (tmp_path / ".scitex" / "dev").mkdir(parents=True)
        (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(yaml_body)
        cfg = load_config(start_path=str(tmp_path))
        return lint_source(_FM001_SRC, str(tmp_path / "fig.py"), cfg)

    def test_scalar_form_promotes_fm001(self, tmp_path):
        # Arrange — scalar project-type form.
        yaml_body = "project-type: research\n"
        # Act
        issues = self._run(tmp_path, yaml_body)
        # Assert
        assert _sev_of(issues, "STX-FM001") == "error"

    def test_block_list_form_promotes_fm001(self, tmp_path):
        # Arrange — block-list project-type form.
        yaml_body = "project-type:\n  - research\n"
        # Act
        issues = self._run(tmp_path, yaml_body)
        # Assert
        assert _sev_of(issues, "STX-FM001") == "error"

    def test_non_research_yaml_keeps_fm001_warning(self, tmp_path):
        # Arrange — pip project; FM enabled explicitly so FM001 fires at default.
        (tmp_path / ".scitex" / "dev").mkdir(parents=True)
        (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(
            "project-type: pip\n"
        )
        cfg = load_config(start_path=str(tmp_path))
        cfg.enable = ["FM"]
        # Act
        issues = lint_source(_FM001_SRC, str(tmp_path / "fig.py"), cfg)
        # Assert
        assert _sev_of(issues, "STX-FM001") == "warning"


# EOF
