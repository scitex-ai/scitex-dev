"""Unit tests for ``scitex_dev._cli.audit._diff``.

Lead task #40 part (b): the diff-aware audit needs three primitives:

1. ``extract_violation_keys`` — parse audit-* stdout into a stable
   ``(rule, file:line, message_excerpt)`` set so HEAD and BASE runs
   can be compared by set arithmetic instead of byte-equal.
2. ``compute_net_new`` — set difference HEAD − BASE.
3. ``filter_to_net_new_lines`` — re-emit only the lines whose keys
   appear in the net-new set, preserving non-finding banner text.

PA-306 no-mocks: real strings parsed by the real regex; no patches.
PA-307: AAA markers + single-assert per test.
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")  # _diff has no Click dep but the package init does


# Representative audit-all stdout fragments — actual shape produced
# by the live `audit-cli` / `audit-project` / siblings.
_HEAD_SAMPLE = """
=== audit-cli ===
ERRO: scitex-todo: 2 error(s)
ERRO:   [PA-306 §3 no-mocks] scitex-todo: tests/scitex_todo/test_reopen.py:43: monkeypatch
ERRO:   [PA-307 §3 test-quality] scitex-todo: tests/scitex_todo/test__model.py:88: TQ007 multi-assert
ERRO:   [PA-307 §3 test-quality] scitex-todo: tests/scitex_todo/test_NEW.py:12: TQ002 missing AAA markers
"""

_BASE_SAMPLE = """
=== audit-cli ===
ERRO: scitex-todo: 2 error(s)
ERRO:   [PA-306 §3 no-mocks] scitex-todo: tests/scitex_todo/test_reopen.py:43: monkeypatch
ERRO:   [PA-307 §3 test-quality] scitex-todo: tests/scitex_todo/test__model.py:88: TQ007 multi-assert
"""


# ---------------------------------------------------------------------------
# extract_violation_keys: identity stays stable across whitespace + ANSI.
# ---------------------------------------------------------------------------


def test_extract_violation_keys_finds_three_in_head():
    """HEAD sample has 3 finding lines → 3 keys."""
    # Arrange
    from scitex_dev._cli.audit._diff import extract_violation_keys

    # Act
    keys = extract_violation_keys(_HEAD_SAMPLE, distribution_filter="scitex-todo")
    # Assert
    assert len(keys) == 3


def test_extract_violation_keys_finds_two_in_base():
    """BASE sample has 2 finding lines → 2 keys."""
    # Arrange
    from scitex_dev._cli.audit._diff import extract_violation_keys

    # Act
    keys = extract_violation_keys(_BASE_SAMPLE, distribution_filter="scitex-todo")
    # Assert
    assert len(keys) == 2


def test_extract_violation_keys_distribution_filter_excludes_others():
    """A finding for a different dist is filtered out."""
    # Arrange
    from scitex_dev._cli.audit._diff import extract_violation_keys

    mixed = _HEAD_SAMPLE + "\nERRO: [PA-101] scitex-io: src/scitex_io/foo.py:9: msg\n"
    # Act
    keys = extract_violation_keys(mixed, distribution_filter="scitex-todo")
    # Assert
    assert len(keys) == 3


def test_extract_violation_keys_ignores_non_finding_banners():
    """Banner / summary lines never produce a key."""
    # Arrange
    from scitex_dev._cli.audit._diff import extract_violation_keys

    only_banner = "=== audit-cli ===\nsummary: audited 1 package(s)\n"
    # Act
    keys = extract_violation_keys(only_banner, distribution_filter="scitex-todo")
    # Assert
    assert len(keys) == 0


# ---------------------------------------------------------------------------
# compute_net_new: HEAD − BASE.
# ---------------------------------------------------------------------------


def test_compute_net_new_returns_only_the_new_finding():
    """3-violation HEAD vs 2-violation BASE → 1 net-new key."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new

    # Act
    net = compute_net_new(
        _HEAD_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo"
    )
    # Assert
    assert len(net) == 1


def test_compute_net_new_identifies_the_correct_rule():
    """The single net-new finding is PA-307 TQ002 on test_NEW.py."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new

    # Act
    net = compute_net_new(
        _HEAD_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo"
    )
    only = next(iter(net))
    # Assert
    assert "TQ002" in only.message_excerpt


def test_compute_net_new_returns_empty_when_head_equals_base():
    """Identical HEAD and BASE outputs → empty net-new (no false positive)."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new

    # Act
    net = compute_net_new(
        _BASE_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo"
    )
    # Assert
    assert net == set()


def test_compute_net_new_returns_empty_when_head_subset_of_base():
    """If BASE has MORE violations than HEAD, net-new is still empty."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new

    # Act
    net = compute_net_new(
        _BASE_SAMPLE, _HEAD_SAMPLE, distribution="scitex-todo"
    )
    # Assert
    assert net == set()


# ---------------------------------------------------------------------------
# filter_to_net_new_lines: re-emit only the matching finding lines.
# ---------------------------------------------------------------------------


def test_filter_to_net_new_lines_keeps_banner():
    """Non-finding lines (banner) are preserved verbatim."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new, filter_to_net_new_lines

    net = compute_net_new(
        _HEAD_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo"
    )
    # Act
    filtered = filter_to_net_new_lines(
        _HEAD_SAMPLE, net, distribution="scitex-todo"
    )
    # Assert
    assert "=== audit-cli ===" in filtered


def test_filter_to_net_new_lines_drops_inherited_finding():
    """Inherited PA-306 violation is suppressed (present in BASE too)."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new, filter_to_net_new_lines

    net = compute_net_new(
        _HEAD_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo"
    )
    # Act
    filtered = filter_to_net_new_lines(
        _HEAD_SAMPLE, net, distribution="scitex-todo"
    )
    # Assert
    assert "monkeypatch" not in filtered


def test_filter_to_net_new_lines_keeps_the_net_new_finding():
    """The net-new TQ002 finding survives the filter."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new, filter_to_net_new_lines

    net = compute_net_new(
        _HEAD_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo"
    )
    # Act
    filtered = filter_to_net_new_lines(
        _HEAD_SAMPLE, net, distribution="scitex-todo"
    )
    # Assert
    assert "TQ002" in filtered


# ---------------------------------------------------------------------------
# worktree_at: real git command, no mocks.
# ---------------------------------------------------------------------------


def _seed_repo(path):
    """Create a minimal real git repo with a `develop` ref + one commit."""
    import subprocess

    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "test"], check=True
    )
    (path / "README.md").write_text("seed\n")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "seed"], check=True
    )
    subprocess.run(
        ["git", "-C", str(path), "branch", "-M", "develop"], check=True
    )


def test_worktree_at_yields_a_real_checkout(tmp_path):
    """`worktree_at` produces a real on-disk checkout for the ref."""
    # Arrange
    from scitex_dev._cli.audit._diff import worktree_at

    repo = tmp_path / "repo"
    repo.mkdir()
    _seed_repo(repo)
    # Act
    with worktree_at(repo, "develop") as base:
        # Assert
        assert (base / "README.md").is_file()


def test_worktree_at_cleans_up_on_exit(tmp_path):
    """The staged tmpdir is removed after the context manager exits."""
    # Arrange
    from scitex_dev._cli.audit._diff import worktree_at

    repo = tmp_path / "repo"
    repo.mkdir()
    _seed_repo(repo)
    # Act
    with worktree_at(repo, "develop") as base:
        captured = base
    # Assert
    assert not captured.exists()


def test_worktree_at_raises_on_unknown_ref(tmp_path):
    """Bad ref → DiffAwareSetupError, not a silent bytes error."""
    # Arrange
    from scitex_dev._cli.audit._diff import DiffAwareSetupError, worktree_at

    repo = tmp_path / "repo"
    repo.mkdir()
    _seed_repo(repo)
    # Act
    # Assert
    with pytest.raises(DiffAwareSetupError):
        with worktree_at(repo, "does-not-exist"):
            pass


def test_worktree_at_raises_when_path_is_not_git(tmp_path):
    """Non-git path → DiffAwareSetupError up-front."""
    # Arrange
    from scitex_dev._cli.audit._diff import DiffAwareSetupError, worktree_at

    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    # Act
    # Assert
    with pytest.raises(DiffAwareSetupError):
        with worktree_at(bare, "develop"):
            pass
