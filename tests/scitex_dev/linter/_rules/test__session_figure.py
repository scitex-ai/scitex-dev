"""Tests for STX-P010 — injected ``plt`` over top-level ``figrecipe``.

Per neurovista handoff 2026-06-14 (Ask 1): inside a module whose
``main(...)`` carries ``@stx.session``, the session already INJECTS a
figrecipe-backed ``plt``. Reaching for a *top-level* ``import figrecipe
as fr`` + ``fr.subplots(...)`` (or any ``fr.<call>``) bypasses that
handle. STX-P010 flags those occurrences and points at the injected
``plt`` — consistent with STX-P007 (drop ``fontsize=``) and STX-FM010
(use ``set_xyt``).

The rule is an ENGINE rule (registered in ``ALL_RULES``, not a
figrecipe-plugin rule) because it is about the ``@stx.session`` injection
contract, the same surface as S001-S008. It must NOT fire when the module
has no ``@stx.session`` main — top-level figrecipe is the correct API
there (a plain plotting script).

Real fixtures only — every assertion runs the genuine ``lint_source``
pipeline over real Python source (no mocks, no monkeypatch; PA-306 / the
no-mock rules). Mirrors the end-to-end style of
``test__session_structure``'s S006 cases, which likewise rely on the real
``requires="scitex"`` gate being satisfied in the test/CI environment.
"""

from scitex_dev.linter._rules import ALL_RULES
from scitex_dev.linter._rules import _session_figure as sf
from scitex_dev.linter.checker import lint_source
from scitex_dev.linter.config import LinterConfig

# A session-decorated main with ALL injected params declared, so the only
# STX-P010-relevant signal in the fixture is the figrecipe usage itself
# (S006 — missing INJECTED — stays quiet and does not muddy the count).
_SESSION_HEAD = (
    "import scitex as stx\n"
    "{imports}"
    "\n"
    "\n"
    "@stx.session\n"
    "def main(\n"
    "    CONFIG=stx.session.INJECTED,\n"
    "    COLORS=stx.session.INJECTED,\n"
    "    logger=stx.session.INJECTED,\n"
    "    plt=stx.session.INJECTED,\n"
    "    rngg=stx.session.INJECTED,\n"
    "):\n"
    "{body}"
    "    return 0\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)


def _session_module(imports: str = "", body: str = "") -> str:
    return _SESSION_HEAD.format(imports=imports, body=body)


def _lint(source: str) -> list:
    return lint_source(source, filepath="examples/plot.py", config=LinterConfig())


def _p010(issues) -> list:
    return [i for i in issues if i.rule.id == "STX-P010"]


# --------------------------------------------------------------------------- #
# Rule object / registration                                                  #
# --------------------------------------------------------------------------- #


def test_p010_registered_in_engine_all_rules():
    # Arrange
    # Act
    rule = ALL_RULES.get("STX-P010")
    # Assert — it must ship from the engine, not depend on a plugin loading.
    assert rule is not None


def test_p010_is_warning_severity_plot_category():
    # Arrange
    rule = sf.P010
    # Act
    # Assert
    assert (rule.severity, rule.category) == ("warning", "plot")


def test_p010_gates_on_scitex():
    # Arrange
    # Act
    # Assert — the injected-plt advice only applies when the umbrella is present.
    assert sf.P010.requires == "scitex"


def test_p010_suggestion_recommends_injected_plt_subplots():
    # Arrange
    suggestion = sf.P010.suggestion
    # Act
    # Assert
    assert "plt.subplots" in suggestion


def test_p010_suggestion_attributes_font_sizes_to_scitex_style():
    # Arrange
    suggestion = sf.P010.suggestion
    # Act
    # Assert
    assert "SCITEX_STYLE" in suggestion


def test_p010_suggestion_says_drop_fontsize_per_stx_p007():
    # Arrange
    suggestion = sf.P010.suggestion
    # Act
    # Assert
    assert "fontsize" in suggestion


def test_p010_suggestion_references_set_xyt_per_stx_fm010():
    # Arrange
    suggestion = sf.P010.suggestion
    # Act
    # Assert
    assert "set_xyt" in suggestion


# --------------------------------------------------------------------------- #
# Positive — fires inside @stx.session                                        #
# --------------------------------------------------------------------------- #


def test_import_figrecipe_as_fr_inside_session_is_flagged():
    # Arrange
    src = _session_module(imports="import figrecipe as fr\n")
    # Act
    issues = _p010(_lint(src))
    # Assert — the top-level import line is one occurrence.
    assert len(issues) == 1


def test_fr_subplots_call_inside_session_is_flagged():
    # Arrange — import + a fr.subplots() call: two distinct fix sites.
    src = _session_module(
        imports="import figrecipe as fr\n",
        body="    fig, ax = fr.subplots()\n",
    )
    # Act
    ids = [i.rule.id for i in _lint(src)]
    # Assert — both the import and the call site flag STX-P010.
    assert ids.count("STX-P010") == 2


def test_direct_figrecipe_subplots_call_inside_session_is_flagged():
    # Arrange — unaliased `import figrecipe` then `figrecipe.subplots()`.
    src = _session_module(
        imports="import figrecipe\n",
        body="    fig, ax = figrecipe.subplots()\n",
    )
    # Act
    count = len(_p010(_lint(src)))
    # Assert — import line + call line.
    assert count == 2


def test_from_figrecipe_import_inside_session_is_flagged():
    # Arrange
    src = _session_module(imports="from figrecipe import subplots\n")
    # Act
    issues = _p010(_lint(src))
    # Assert
    assert len(issues) == 1


def test_chained_figrecipe_call_inside_session_is_flagged():
    # Arrange — `fr.figure()` is a figrecipe call; the chained `.savefig`
    # on the returned local is NOT (it does not resolve to figrecipe).
    src = _session_module(
        imports="import figrecipe as fr\n",
        body="    fig = fr.figure()\n",
    )
    # Act
    count = len(_p010(_lint(src)))
    # Assert — import line + the fr.figure() call line.
    assert count == 2


def test_p010_message_points_at_injected_plt():
    # Arrange
    src = _session_module(imports="import figrecipe as fr\n")
    # Act
    issues = _p010(_lint(src))
    # Assert
    assert "session-injected" in issues[0].rule.message


# --------------------------------------------------------------------------- #
# Negative — must NOT fire                                                     #
# --------------------------------------------------------------------------- #


def test_injected_plt_subplots_inside_session_is_not_flagged():
    # Arrange — the canonical correct pattern: use the injected plt.
    src = _session_module(
        body="    fig, ax = plt.subplots()\n    ax.plot([1, 2, 3])\n",
    )
    # Act
    issues = _p010(_lint(src))
    # Assert
    assert issues == []


def test_top_level_figrecipe_without_session_is_not_flagged():
    # Arrange — a plain plotting script (no @stx.session): top-level
    # figrecipe is the CORRECT API and must not be flagged.
    src = 'import figrecipe as fr\n\nfig, ax = fr.subplots()\nfr.save(fig, "out.png")\n'
    # Act
    issues = _p010(lint_source(src, filepath="scratch.py", config=LinterConfig()))
    # Assert
    assert issues == []


def test_stx_allow_comment_suppresses_p010_on_import_line():
    # Arrange — the standard per-line escape hatch must silence the import.
    src = _session_module(
        imports="import figrecipe as fr  # stx-allow: STX-P010\n",
    )
    # Act
    issues = _p010(_lint(src))
    # Assert
    assert issues == []
