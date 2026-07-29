"""Tests for figure-family severity promotion under ``project-type: research``.

v1 (operator directive 2026-06-28): the linter already DETECTS figure-bypass
patterns (figrecipe owns detection); these tests pin the new SEVERITY wiring
that promotes the EXISTING figure-family rules to ERROR in research projects
so the post-edit hook (run_lint.sh, exit 2) BLOCKS figure-bypass code.

The promoted set is defined BY CATEGORY, not by rule id: every rule carrying
category ``figure`` or ``plot`` promotes, whoever declares and emits it. Do not
re-introduce an id enumeration here — the one that used to live in this
docstring ("figure: STX-FM001..FM011 + STX-FIG001") silently rotted as figrecipe
grew FM016-FM019. Measured 2026-07-29, figrecipe declares:
- category ``figure``: STX-FM001..FM011, STX-FM016..FM019, STX-FIG001
- category ``plot``:   STX-P001..P009
…and that list is expected to keep growing, which is the point.

Two emit paths feed one combined issue list:
- ``SciTeXChecker._add`` / ``FMChecker._add`` (scitex-dev) — these apply the
  category override themselves, at emit time.
- every figrecipe plugin checker's ``_emit`` (read-only here) — these honour
  ``per_rule_severity`` ONLY, so they depend entirely on the central floor.

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
        _skip_if_not_emitted(issues, "STX-FM001")
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
        _skip_if_not_emitted(issues, "STX-FM001")
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
        _skip_if_not_emitted(issues, "STX-FM001")
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
        _skip_if_not_emitted(issues, "STX-FM001")
        # Assert
        assert _sev_of(issues, "STX-FM001") == "error"

    def test_block_list_form_promotes_fm001(self, tmp_path):
        # Arrange — block-list project-type form.
        yaml_body = "project-type:\n  - research\n"
        # Act
        issues = self._run(tmp_path, yaml_body)
        _skip_if_not_emitted(issues, "STX-FM001")
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
        _skip_if_not_emitted(issues, "STX-FM001")
        # Assert
        assert _sev_of(issues, "STX-FM001") == "warning"


# ---------------------------------------------------------------------- #
# Regression: files under `scripts/` must promote too (clew, 2026-07-29)  #
# ---------------------------------------------------------------------- #
#
# ``is_script()`` returns False for anything under a configured
# ``script_dirs`` / ``library_dirs`` entry, and ``get_issues`` used to
# early-return on that branch BEFORE applying the category floor. In a
# research repo essentially ALL figure code lives under ``scripts/``, so the
# whole promotion was inert exactly where it mattered: rules emitted through
# ``_add`` (FM001-FM009 / P001-P005) showed as ERROR while every
# plugin-emitted rule in the SAME file (FM010/FM011/FM016/FM019, P006-P009)
# stayed WARNING.
#
# These tests do NOT require figrecipe: they drive ``lint_source``'s documented
# ``plugins=`` payload seam with a REAL checker that reproduces the figrecipe
# emit contract (honour ``per_rule_severity``, ignore the category override).
# Real tmp trees, real ``.scitex/dev/config.yaml`` — no monkeypatch, no mocks.


_PLUGIN_RULE_IDS = ("STX-FM010", "STX-FM011", "STX-FM016")


def _plugin_payload():
    """A real plugin payload mirroring figrecipe's checker contract.

    figrecipe's ``FigureMethodChecker`` / ``RawMplBypassChecker`` resolve
    severity from ``config.per_rule_severity`` ONLY — they never consult
    ``category_severity_override``. This checker does the same, so whatever
    severity these rules end up with comes from the engine's central floor,
    which is precisely what is under test.
    """
    import ast
    from dataclasses import replace as _replace

    from scitex_dev.linter.checker import _is_allowed_by_comment

    rules = {
        rid: Rule(
            id=rid,
            severity="warning",
            category="figure",
            message=f"{rid} message",
            suggestion=f"{rid} suggestion",
        )
        for rid in _PLUGIN_RULE_IDS
    }

    class PluginFigureChecker(ast.NodeVisitor):
        category = "figure"

        def __init__(self, source_lines, config):
            self.source_lines = source_lines
            self.config = config
            self.issues: list = []

        def _emit(self, rule, node):
            line = ""
            if 1 <= node.lineno <= len(self.source_lines):
                line = self.source_lines[node.lineno - 1].rstrip()
            if rule.id in self.config.disable:
                return
            if _is_allowed_by_comment(line, rule.id):
                return
            sev = self.config.per_rule_severity.get(rule.id)
            if sev:
                rule = _replace(rule, severity=sev)
            self.issues.append(
                Issue(rule=rule, line=node.lineno, col=node.col_offset,
                      source_line=line)
            )

        def visit_Call(self, node):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr == "set_xlabel":
                    self._emit(rules["STX-FM010"], node)
                elif func.attr == "set_visible":
                    self._emit(rules["STX-FM011"], node)
                elif func.attr == "subplots":
                    self._emit(rules["STX-FM016"], node)
            self.generic_visit(node)

    return {
        "rules": list(rules.values()),
        "call_rules": {},
        "axes_hints": {},
        "checkers": [PluginFigureChecker],
    }


_PLUGIN_SRC = (
    "import matplotlib.pyplot as plt\n"
    "fig, ax = plt.subplots()\n"
    "ax.set_xlabel('x')\n"
    "ax.spines['top'].set_visible(False)\n"
)


def _make_tree(tmp_path, project_type):
    """Create a REAL project tree declaring *project_type*, with a scripts/ dir."""
    (tmp_path / ".scitex" / "dev").mkdir(parents=True)
    (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(
        f"project-type: {project_type}\n"
    )
    (tmp_path / "scripts").mkdir()
    return tmp_path


def _lint_at(path, tmp_path, *, force_enable_fm=False):
    """Lint ``_PLUGIN_SRC`` as *path*, with config resolved from that file."""
    cfg = load_config(start_path=str(path))
    if force_enable_fm and "FM" not in cfg.enable:
        cfg.enable = [*cfg.enable, "FM"]
    return lint_source(_PLUGIN_SRC, str(path), cfg, plugins=_plugin_payload())


class TestScriptDirFilesPromoteToo:
    """Plugin-emitted figure rules promote for files under ``scripts/`` too."""

    @pytest.mark.parametrize("rule_id", _PLUGIN_RULE_IDS)
    def test_scripts_dir_file_promotes_in_research(self, tmp_path, rule_id):
        # Arrange — research tree; the file lives under scripts/ (is_script
        # False), which is where a research repo's figure code actually lives.
        root = _make_tree(tmp_path, "research")
        target = root / "scripts" / "make_figure.py"
        # Act
        issues = _lint_at(target, root)
        # Assert
        assert _sev_of(issues, rule_id) == "error", (
            f"{rule_id} under scripts/ must promote to error in a research "
            f"project; got {[(i.rule.id, i.rule.severity) for i in issues]}"
        )

    @pytest.mark.parametrize("rule_id", _PLUGIN_RULE_IDS)
    def test_non_scripts_file_promotes_in_research(self, tmp_path, rule_id):
        # Arrange — control for the LOCATION axis: same research tree, but the
        # file is a plain script (is_script True). This path always worked.
        root = _make_tree(tmp_path, "research")
        target = root / "make_figure.py"
        # Act
        issues = _lint_at(target, root)
        # Assert
        assert _sev_of(issues, rule_id) == "error"

    @pytest.mark.parametrize("rule_id", _PLUGIN_RULE_IDS)
    def test_non_research_scripts_dir_stays_warning(self, tmp_path, rule_id):
        # Arrange — POSITIVE CONTROL for the PROJECT-TYPE axis: an identical
        # tree that is NOT research. Without this, "error everywhere" would be
        # indistinguishable from a working promotion.
        root = _make_tree(tmp_path, "pip")
        target = root / "scripts" / "make_figure.py"
        # Act
        issues = _lint_at(target, root, force_enable_fm=True)
        # Assert
        assert _sev_of(issues, rule_id) == "warning", (
            f"{rule_id} must stay warning outside a research project; "
            f"got {[(i.rule.id, i.rule.severity) for i in issues]}"
        )

    @staticmethod
    def _pin_fm010_to_warning(tmp_path):
        """Research tree + a scripts/ file, with FM010 pinned to warning."""
        root = _make_tree(tmp_path, "research")
        target = root / "scripts" / "make_figure.py"
        cfg = load_config(start_path=str(target))
        cfg.per_rule_severity = {**cfg.per_rule_severity, "STX-FM010": "warning"}
        return target, cfg

    def test_per_rule_pin_keeps_fm010_warning_under_scripts(self, tmp_path):
        # Arrange
        target, cfg = self._pin_fm010_to_warning(tmp_path)
        # Act
        issues = lint_source(
            _PLUGIN_SRC, str(target), cfg, plugins=_plugin_payload()
        )
        # Assert — the operator's per-rule pin wins over the category floor.
        assert _sev_of(issues, "STX-FM010") == "warning"

    def test_unpinned_neighbour_still_promotes_under_scripts(self, tmp_path):
        # Arrange — same setup; FM011 carries no pin.
        target, cfg = self._pin_fm010_to_warning(tmp_path)
        # Act
        issues = lint_source(
            _PLUGIN_SRC, str(target), cfg, plugins=_plugin_payload()
        )
        # Assert — pinning one rule must not disarm the floor for the rest.
        assert _sev_of(issues, "STX-FM011") == "error"

    def test_stx_allow_still_suppresses_under_scripts(self, tmp_path):
        # Arrange — the per-line opt-out must survive the floor, not be
        # resurrected by it.
        root = _make_tree(tmp_path, "research")
        target = root / "scripts" / "make_figure.py"
        cfg = load_config(start_path=str(target))
        src = "ax.set_xlabel('x')  # stx-allow: STX-FM010\n"
        # Act
        issues = lint_source(src, str(target), cfg, plugins=_plugin_payload())
        # Assert
        assert _sev_of(issues, "STX-FM010") is None


# EOF
