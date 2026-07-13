"""Tests for the linter's TQ (test-quality) detection helpers.

Locks in the behaviour of `_tq001_function_has_assertion`,
`_tq002_missing_aaa_markers`, `_tq003_name_word_count`,
`_tq007_count_assertions`, and the rule-emission glue in
`SciTeXChecker`. Every test below itself follows TQ001-007.
"""

from __future__ import annotations

from scitex_dev.linter.checker import lint_source


# ── helpers ──────────────────────────────────────────────────────────────────


def _ids(src: str) -> list[str]:
    """Return STX-TQ rule ids fired on `src`, parsed as a test file."""
    issues = lint_source(
        src,
        filepath="/home/ywatanabe/proj/scitex-dev/tests/scitex_dev/_demo.py",
    )
    return [i.rule.id for i in issues if i.rule.id.startswith("STX-TQ")]


# ── TQ001 — empty assertion ─────────────────────────────────────────────────


def test_tq001_fires_when_test_body_has_no_assert():
    # Arrange
    src = (
        "def test_returns_a_callable_module_object():\n"
        "    # Arrange\n"
        "    # Act\n"
        "    # Assert\n"
        "    x = 1\n"
        "    y = x + 1\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ001" in fired


def test_tq001_silent_when_pytest_raises_used_as_assertion():
    # Arrange
    src = (
        "import pytest\n"
        "def test_raises_value_error_on_bad_input():\n"
        "    # Arrange\n"
        "    # Act\n"
        "    # Assert\n"
        "    with pytest.raises(ValueError):\n"
        "        int('notanint')\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ001" not in fired


def test_tq001_silent_when_skip_decorated_stub_has_no_assertion():
    # Arrange — a `@pytest.mark.skip(...)` body never runs under pytest,
    # so "no assertion" is not a meaningful signal for it.
    src = (
        "import pytest\n"
        "@pytest.mark.skip(reason='not implemented yet')\n"
        "def test_computes_future_feature_correctly():\n"
        "    pass\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ001" not in fired


def test_tq001_silent_when_bare_skip_decorated_stub_has_no_assertion():
    # Arrange — bare `@pytest.mark.skip` (no call, no reason) form.
    src = (
        "import pytest\n"
        "@pytest.mark.skip\n"
        "def test_computes_future_feature_correctly():\n"
        "    pass\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ001" not in fired


def test_tq001_silent_when_skipif_decorated_stub_has_no_assertion():
    # Arrange — `@pytest.mark.skipif(...)` body never runs under pytest
    # either, when the condition is true at collection time.
    src = (
        "import sys\n"
        "import pytest\n"
        "@pytest.mark.skipif(sys.platform == 'win32', reason='posix only')\n"
        "def test_computes_posix_only_feature_correctly():\n"
        "    pass\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ001" not in fired


# ── TQ002 — AAA marker enforcement ───────────────────────────────────────────


def test_tq002_fires_when_arrange_marker_is_missing():
    # Arrange
    src = (
        "def test_returns_one_plus_one_equals_two():\n"
        "    # Act\n"
        "    y = 1 + 1\n"
        "    # Assert\n"
        "    assert y == 2\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ002" in fired


def test_tq002_fires_when_markers_are_out_of_order():
    # Arrange
    src = (
        "def test_returns_one_plus_one_equals_two():\n"
        "    # Act\n"
        "    y = 1 + 1\n"
        "    # Arrange\n"
        "    x = 1\n"
        "    # Assert\n"
        "    assert y == 2\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ002" in fired


def test_tq002_silent_when_markers_present_and_ordered():
    # Arrange
    src = (
        "def test_returns_one_plus_one_equals_two():\n"
        "    # Arrange\n"
        "    x = 1\n"
        "    # Act\n"
        "    y = x + 1\n"
        "    # Assert\n"
        "    assert y == 2\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ002" not in fired


def test_tq002_fires_when_markers_are_combined_on_one_line():
    # Arrange — combined form `# Arrange / Act / Assert` is rejected;
    # each marker must appear on its own line in order.
    src = (
        "def test_returns_one_plus_one_equals_two():\n"
        "    # Arrange / Act / Assert\n"
        "    x = 1\n"
        "    y = x + 1\n"
        "    assert y == 2\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ002" in fired


def test_tq002_allows_descriptive_text_after_keyword():
    # Arrange — descriptive suffix should not change detection
    src = (
        "def test_returns_one_plus_one_equals_two():\n"
        "    # Arrange: build the inputs\n"
        "    x = 1\n"
        "    # Act: invoke the operation under test\n"
        "    y = x + 1\n"
        "    # Assert: result matches expectation\n"
        "    assert y == 2\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ002" not in fired


# ── TQ003 — descriptive name (≥3 word-tokens) ────────────────────────────────


def test_tq003_fires_on_one_word_test_name():
    # Arrange
    src = "def test_foo():\n    # Arrange\n    # Act\n    # Assert\n    assert True\n"
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ003" in fired


def test_tq003_fires_on_two_word_test_name():
    # Arrange
    src = (
        "def test_returns_dict():\n"
        "    # Arrange\n"
        "    # Act\n"
        "    # Assert\n"
        "    assert True\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ003" in fired


def test_tq003_silent_on_three_word_test_name():
    # Arrange
    src = (
        "def test_returns_empty_dict():\n"
        "    # Arrange\n"
        "    # Act\n"
        "    # Assert\n"
        "    assert True\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ003" not in fired


# ── TQ007 — exactly one assertion per test ───────────────────────────────────


def test_tq007_fires_on_two_bare_assert_statements():
    # Arrange
    src = (
        "def test_returns_pair_with_correct_first_and_second():\n"
        "    # Arrange\n"
        "    pair = (1, 2)\n"
        "    # Act\n"
        "    # Assert\n"
        "    assert pair[0] == 1\n"
        "    assert pair[1] == 2\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ007" in fired


def test_tq007_fires_on_assert_plus_pytest_raises():
    # Arrange
    src = (
        "import pytest\n"
        "def test_returns_pair_or_raises_under_condition():\n"
        "    # Arrange\n"
        "    # Act\n"
        "    # Assert\n"
        "    assert True\n"
        "    with pytest.raises(ValueError):\n"
        "        int('x')\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ007" in fired


def test_tq007_silent_on_single_assert_statement():
    # Arrange
    src = (
        "def test_returns_one_plus_one_equals_two():\n"
        "    # Arrange\n"
        "    x = 1\n"
        "    # Act\n"
        "    y = x + 1\n"
        "    # Assert\n"
        "    assert y == 2\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ007" not in fired


def test_tq007_silent_on_lone_pytest_raises_block():
    # Arrange
    src = (
        "import pytest\n"
        "def test_raises_value_error_on_bad_input():\n"
        "    # Arrange\n"
        "    # Act\n"
        "    # Assert\n"
        "    with pytest.raises(ValueError):\n"
        "        int('x')\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ007" not in fired


# ── TQ004 — session-scope fixture with state mutation ────────────────────────


def test_tq004_fires_on_session_scope_fixture_with_write_text_call():
    # Arrange
    src = (
        "import pytest\n"
        "@pytest.fixture(scope='session')\n"
        "def shared_payload(tmp_path):\n"
        "    p = tmp_path / 'x'\n"
        "    p.write_text('hi')\n"
        "    yield p\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ004" in fired


# ── TQ005 — fixture with return-not-yield around a resource ─────────────────


def test_tq005_fires_when_open_resource_returned_instead_of_yielded():
    # Arrange
    src = (
        "import pytest\n"
        "@pytest.fixture\n"
        "def my_handle():\n"
        "    handle = open('/tmp/x')\n"
        "    return handle\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ005" in fired


# ── TQ006 — parametrize body with top-level if ───────────────────────────────


def test_tq006_fires_on_parametrize_with_should_raise_branch():
    # Arrange
    src = (
        "import pytest\n"
        "@pytest.mark.parametrize('x,r', [(1, False), (None, True)])\n"
        "def test_either_returns_value_or_raises(x, r):\n"
        "    # Arrange\n"
        "    # Act\n"
        "    # Assert\n"
        "    if r:\n"
        "        with pytest.raises(TypeError):\n"
        "            int(x)\n"
        "    else:\n"
        "        assert int(x) == x\n"
    )
    # Act
    fired = _ids(src)
    # Assert
    assert "STX-TQ006" in fired
