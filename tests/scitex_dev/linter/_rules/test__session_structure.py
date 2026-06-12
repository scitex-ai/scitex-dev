"""Tests for the in-house STX-S001-S008 structure rules.

Absorbed from the scitex-umbrella plugin (``scitex._linter_plugin``)
into the engine registry (umbrella-thinning Phase A). They must be
discoverable straight from ``scitex_dev.linter._rules.ALL_RULES``.

The ``requires`` gate is intentionally NOT uniform — verbatim from the
former umbrella plugin: S001/S003/S004/S005/S006 reference
``@stx.session`` / ``import scitex`` and gate on ``requires="scitex"``,
while S002/S007/S008 are generic structure/naming checks with no gate.
"""

import pytest

from scitex_dev.linter._rules import ALL_RULES
from scitex_dev.linter._rules import _session_structure as ss

S_RULES = [
    ss.S001,
    ss.S002,
    ss.S003,
    ss.S004,
    ss.S005,
    ss.S006,
    ss.S007,
    ss.S008,
]
S_IDS = [f"STX-S00{i}" for i in range(1, 9)]

# Verbatim gating preserved from the former umbrella plugin.
SCITEX_GATED = {"STX-S001", "STX-S003", "STX-S004", "STX-S005", "STX-S006"}
UNGATED = {"STX-S002", "STX-S007", "STX-S008"}


@pytest.mark.parametrize("rule_id", S_IDS)
def test_structure_rule_is_registered_in_all_rules(rule_id):
    # Arrange
    # Act
    rule = ALL_RULES.get(rule_id)
    # Assert
    assert rule is not None, f"{rule_id} not in engine ALL_RULES"


@pytest.mark.parametrize("rule_id", sorted(SCITEX_GATED))
def test_scitex_gated_structure_rule_requires_scitex(rule_id):
    # Arrange
    rule = ALL_RULES[rule_id]
    # Act
    # Assert
    assert rule.requires == "scitex"


@pytest.mark.parametrize("rule_id", sorted(UNGATED))
def test_generic_structure_rule_is_ungated(rule_id):
    """S002/S007/S008 fire regardless of scitex install — verbatim behavior."""
    # Arrange
    rule = ALL_RULES[rule_id]
    # Act
    # Assert
    assert rule.requires == ""


@pytest.mark.parametrize("rule", S_RULES)
def test_structure_rule_category_is_structure(rule):
    # Arrange
    # Act
    # Assert
    assert rule.category == "structure"


def test_module_exposes_all_eight_structure_rule_ids():
    # Arrange
    # Act
    got = sorted(r.id for r in S_RULES)
    # Assert
    assert got == sorted(S_IDS)


def test_s001_is_error_severity():
    # Arrange
    # Act
    # Assert
    assert ALL_RULES["STX-S001"].severity == "error"


# ---------------------------------------------------------------------- #
# STX-S006 behavioural — #60 regression + kwonly/posonly detection.       #
# ---------------------------------------------------------------------- #
# The legacy scitex._linter_plugin S006 dereferenced .id on the default-
# value / annotation AST of each injected param, which NPE'd on any
# real-world @stx.session script that used annotated args or stx.session.
# INJECTED defaults (the canonical pattern). umbrella-thinning Phase A
# (commit 4beb9f4) rewrote S006 to compare arg.arg name strings only —
# never the value/annotation node — eliminating the .id-on-None path.
# These tests pin that behaviour: lint_source MUST NOT raise on the
# neurovista repro, AND S006 MUST detect INJECTED params declared as
# keyword-only (behind `*`) or positional-only (after `/`).


def _lint(source: str) -> list:
    """Lint a snippet with the default config; return Issues."""
    from scitex_dev.linter.checker import lint_source
    from scitex_dev.linter.config import LinterConfig

    return lint_source(source, filepath="<test>", config=LinterConfig())


def _s006_issues(issues) -> list:
    return [i for i in issues if i.rule.id == "STX-S006"]


def test_s006_neurovista_pattern_does_not_raise_npe():
    """#60 — annotated args + INJECTED defaults must not NPE on .id."""
    # Arrange
    source = (
        "import scitex as stx\n"
        "\n"
        "@stx.session\n"
        "def main(\n"
        "    data_path: str,\n"
        "    threshold: float = 0.5,\n"
        "    CONFIG=stx.session.INJECTED,\n"
        "    plt=stx.session.INJECTED,\n"
        "    COLORS=stx.session.INJECTED,\n"
        "    rngg=stx.session.INJECTED,\n"
        "    logger=stx.session.INJECTED,\n"
        "):\n"
        "    return 0\n"
    )
    # Act
    issues = _lint(source)
    # Assert
    assert _s006_issues(issues) == [], "all 5 INJECTED declared — S006 must not fire"


def test_s006_detects_keyword_only_injected_params():
    """S006 must see INJECTED params declared behind a `*` separator."""
    # Arrange
    source = (
        "import scitex as stx\n"
        "\n"
        "@stx.session\n"
        "def main(\n"
        "    *,\n"
        "    CONFIG=stx.session.INJECTED,\n"
        "    plt=stx.session.INJECTED,\n"
        "    COLORS=stx.session.INJECTED,\n"
        "    rngg=stx.session.INJECTED,\n"
        "    logger=stx.session.INJECTED,\n"
        "):\n"
        "    return 0\n"
    )
    # Act
    issues = _s006_issues(_lint(source))
    # Assert
    assert issues == [], "kwonly INJECTED params must count toward declared set"


def test_s006_detects_positional_only_injected_params():
    """S006 must see INJECTED params declared before a `/` separator."""
    # Arrange
    source = (
        "import scitex as stx\n"
        "\n"
        "@stx.session\n"
        "def main(\n"
        "    CONFIG=stx.session.INJECTED,\n"
        "    plt=stx.session.INJECTED,\n"
        "    /,\n"
        "    COLORS=stx.session.INJECTED,\n"
        "    rngg=stx.session.INJECTED,\n"
        "    logger=stx.session.INJECTED,\n"
        "):\n"
        "    return 0\n"
    )
    # Act
    issues = _s006_issues(_lint(source))
    # Assert
    assert issues == [], "posonly INJECTED params must count toward declared set"


def test_s006_still_fires_on_actually_missing_injected_params():
    """Sanity guard — the fix must not silence S006 when params ARE missing."""
    # Arrange
    source = (
        "import scitex as stx\n"
        "\n"
        "@stx.session\n"
        "def main(CONFIG=stx.session.INJECTED, plt=stx.session.INJECTED):\n"
        "    return 0\n"
    )
    expected_missing = ("COLORS", "rngg", "logger")
    # Act
    issues = _s006_issues(_lint(source))
    msg = issues[0].rule.message if issues else ""
    # Assert
    assert len(issues) == 1 and all(p in msg for p in expected_missing), (
        f"expected exactly 1 S006 listing {expected_missing} as missing; "
        f"got {len(issues)} issue(s), message={msg!r}"
    )


def test_s006_handles_bare_function_without_any_args():
    """`def main():` with @stx.session — no NPE, S006 lists all 5 missing."""
    # Arrange
    source = (
        "import scitex as stx\n"
        "\n"
        "@stx.session\n"
        "def main():\n"
        "    return 0\n"
    )
    expected_missing = ("CONFIG", "plt", "COLORS", "rngg", "logger")
    # Act
    issues = _s006_issues(_lint(source))
    msg = issues[0].rule.message if issues else ""
    # Assert
    assert len(issues) == 1 and all(p in msg for p in expected_missing), (
        f"expected exactly 1 S006 listing all 5 INJECTED params as missing; "
        f"got {len(issues)} issue(s), message={msg!r}"
    )
