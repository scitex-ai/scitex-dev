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
    """HEAD sample: 3 parsed findings + 1 UNPARSED summary line → 4 keys.

    Count changed from 3 by the fail-open fix (2026-07-29). The extra
    key is ``ERRO: scitex-todo: 2 error(s)`` — an ERRO line
    ``_FINDING_RE`` cannot parse, which previously vanished. It now
    keys as ``UNPARSED`` so an error can never contribute nothing to
    the exit code. It appears in BASE too, so net-new is unchanged.
    """
    # Arrange
    from scitex_dev._cli.audit._diff import extract_violation_keys

    # Act
    keys = extract_violation_keys(_HEAD_SAMPLE, distribution_filter="scitex-todo")
    # Assert
    assert len(keys) == 4


def test_extract_violation_keys_finds_two_in_base():
    """BASE sample: 2 parsed findings + 1 UNPARSED summary line → 3 keys.

    Same +1 as the HEAD case; see that test for why.
    """
    # Arrange
    from scitex_dev._cli.audit._diff import extract_violation_keys

    # Act
    keys = extract_violation_keys(_BASE_SAMPLE, distribution_filter="scitex-todo")
    # Assert
    assert len(keys) == 3


def test_extract_violation_keys_distribution_filter_excludes_others():
    """A PARSED finding for a different dist is still filtered out.

    The appended ``scitex-io`` line parses, so its dist is readable and
    the filter drops it — that contract is unchanged. The count is 4
    rather than 3 only because HEAD's own unparsable summary line now
    keys (see ``test_extract_violation_keys_finds_three_in_head``).

    Note the deliberate asymmetry, pinned by
    ``test_unparsable_erro_survives_a_distribution_filter``: an
    UNPARSED line is NOT filtered, because its dist is unknown and
    "I cannot tell whose this is" must not collapse into "not theirs".
    """
    # Arrange
    from scitex_dev._cli.audit._diff import extract_violation_keys

    mixed = _HEAD_SAMPLE + "\nERRO: [PA-101] scitex-io: src/scitex_io/foo.py:9: msg\n"
    # Act
    keys = extract_violation_keys(mixed, distribution_filter="scitex-todo")
    # Assert
    assert len(keys) == 4


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
    net = compute_net_new(_HEAD_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo")
    # Assert
    assert len(net) == 1


def test_compute_net_new_identifies_the_correct_rule():
    """The single net-new finding is PA-307 TQ002 on test_NEW.py."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new

    # Act
    net = compute_net_new(_HEAD_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo")
    only = next(iter(net))
    # Assert
    assert "TQ002" in only.message_excerpt


def test_compute_net_new_returns_empty_when_head_equals_base():
    """Identical HEAD and BASE outputs → empty net-new (no false positive)."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new

    # Act
    net = compute_net_new(_BASE_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo")
    # Assert
    assert net == set()


def test_compute_net_new_returns_empty_when_head_subset_of_base():
    """If BASE has MORE violations than HEAD, net-new is still empty."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new

    # Act
    net = compute_net_new(_BASE_SAMPLE, _HEAD_SAMPLE, distribution="scitex-todo")
    # Assert
    assert net == set()


# ---------------------------------------------------------------------------
# filter_to_net_new_lines: re-emit only the matching finding lines.
# ---------------------------------------------------------------------------


def test_filter_to_net_new_lines_keeps_banner():
    """Non-finding lines (banner) are preserved verbatim."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new, filter_to_net_new_lines

    net = compute_net_new(_HEAD_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo")
    # Act
    filtered = filter_to_net_new_lines(_HEAD_SAMPLE, net, distribution="scitex-todo")
    # Assert
    assert "=== audit-cli ===" in filtered


def test_filter_to_net_new_lines_drops_inherited_finding():
    """Inherited PA-306 violation is suppressed (present in BASE too)."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new, filter_to_net_new_lines

    net = compute_net_new(_HEAD_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo")
    # Act
    filtered = filter_to_net_new_lines(_HEAD_SAMPLE, net, distribution="scitex-todo")
    # Assert
    assert "monkeypatch" not in filtered


def test_filter_to_net_new_lines_keeps_the_net_new_finding():
    """The net-new TQ002 finding survives the filter."""
    # Arrange
    from scitex_dev._cli.audit._diff import compute_net_new, filter_to_net_new_lines

    net = compute_net_new(_HEAD_SAMPLE, _BASE_SAMPLE, distribution="scitex-todo")
    # Act
    filtered = filter_to_net_new_lines(_HEAD_SAMPLE, net, distribution="scitex-todo")
    # Assert
    assert "TQ002" in filtered


# ---------------------------------------------------------------------------
# worktree_at: real git command, no mocks.
# ---------------------------------------------------------------------------


def _seed_repo(path):
    """Create a minimal real git repo with a `develop` ref + one commit.

    Every git subprocess runs with GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM pinned to
    os.devnull and an explicit author/committer identity in the env. A shared CI
    runner whose global or system gitconfig is missing/unreadable would otherwise
    make even ``git add`` fail with "fatal: unknown error occurred while reading
    the configuration files" (observed as a flake on the pooled self-hosted
    runner, 2026-07-20). Pinning the config paths makes the test independent of
    the host's git configuration.
    """
    import os
    import subprocess

    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }

    def _git(*args):
        subprocess.run(["git", *args], check=True, env=env)

    _git("init", "-q", str(path))
    _git("-C", str(path), "config", "user.email", "test@example.com")
    _git("-C", str(path), "config", "user.name", "test")
    (path / "README.md").write_text("seed\n")
    _git("-C", str(path), "add", ".")
    _git("-C", str(path), "commit", "-q", "-m", "seed")
    _git("-C", str(path), "branch", "-M", "develop")


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


# ---------------------------------------------------------------------------
# Line-stable identity (2026-06-13 lead-directed refinement). The ratchet's
# whole job is "fail only on NEW debt"; if a one-line docstring tweak above
# a flagged construct re-keys every finding in that file as "new", the
# ratchet churns and every unrelated PR gets a false-positive CI failure.
# These sentinels pin the line-stable identity so that regression never
# slips back in.
# ---------------------------------------------------------------------------


# Same content as the BASE/HEAD samples above but with EVERY line number
# bumped (e.g. ``test_reopen.py:43`` → ``test_reopen.py:87``). Models
# the "an unrelated edit above a flagged construct shifts every lineno
# downward" scenario. The line-stable identity MUST treat these as
# IDENTICAL to the base sample (no net-new).
_BASE_SAMPLE_LINENOS_SHIFTED = """
=== audit-cli ===
ERRO: scitex-todo: 2 error(s)
ERRO:   [PA-306 §3 no-mocks] scitex-todo: tests/scitex_todo/test_reopen.py:87: monkeypatch
ERRO:   [PA-307 §3 test-quality] scitex-todo: tests/scitex_todo/test__model.py:204: TQ007 multi-assert
"""


def test_extract_keys_stable_under_lineno_shift_collisions():
    # Arrange — same logical violations, different line numbers.
    from scitex_dev._cli.audit._diff import extract_violation_keys

    base_keys = extract_violation_keys(_BASE_SAMPLE, distribution_filter="scitex-todo")
    shifted_keys = extract_violation_keys(
        _BASE_SAMPLE_LINENOS_SHIFTED, distribution_filter="scitex-todo"
    )
    # Act
    # Assert — the two key sets are EQUAL, not just same-cardinality.
    assert base_keys == shifted_keys


def test_compute_net_new_empty_when_only_linenos_shifted():
    # Arrange — the ratchet's primary failure mode: an unrelated edit
    # bumps every lineno; without line-stable identity, compute_net_new
    # would return the entire base-sample finding set as "new".
    from scitex_dev._cli.audit._diff import compute_net_new

    # Act
    net = compute_net_new(
        _BASE_SAMPLE_LINENOS_SHIFTED,
        _BASE_SAMPLE,
        distribution="scitex-todo",
    )
    # Assert
    assert net == set()


def test_violation_key_file_component_drops_trailing_lineno():
    # Arrange — direct unit on the key shape so a regression points
    # straight at the file component.
    from scitex_dev._cli.audit._diff import extract_violation_keys

    keys = extract_violation_keys(_BASE_SAMPLE, distribution_filter="scitex-todo")
    # Act
    file_components = {k.file_line for k in keys}
    # Assert — every component is a bare path (no ``:NN`` suffix).
    assert all(":" not in fc.rsplit("/", 1)[-1] for fc in file_components)


def test_violation_key_message_excerpt_drops_embedded_lineno():
    # Arrange — sentinel for the rule-class where the auditor's
    # ``msg`` field itself embeds a line ref (some rules append
    # ``... at line 88`` or a redundant ``:NN:``). Normalization must
    # scrub those too so the message excerpt is line-stable.
    from scitex_dev._cli.audit._diff import extract_violation_keys

    sample = (
        "ERRO:   [PA-307 §3 test-quality] scitex-todo: tests/scitex_todo/x.py: "
        "TQ007 at line 88 — multi-assert\n"
    )
    sample2 = (
        "ERRO:   [PA-307 §3 test-quality] scitex-todo: tests/scitex_todo/x.py: "
        "TQ007 at line 204 — multi-assert\n"
    )
    # Act
    keys1 = extract_violation_keys(sample, distribution_filter="scitex-todo")
    keys2 = extract_violation_keys(sample2, distribution_filter="scitex-todo")
    # Assert — same logical finding, two different line refs in the
    # message; identity must collapse them.
    assert keys1 == keys2


def test_filter_to_net_new_lines_drops_inherited_under_lineno_shift():
    # Arrange — ratchet end-to-end sentinel: even if HEAD's linenos
    # have shifted from BASE's, the inherited findings stay filtered
    # out (not re-introduced as false positives).
    from scitex_dev._cli.audit._diff import (
        compute_net_new,
        filter_to_net_new_lines,
    )

    # HEAD = BASE-shape but with shifted linenos (no actual new violations).
    net = compute_net_new(
        _BASE_SAMPLE_LINENOS_SHIFTED,
        _BASE_SAMPLE,
        distribution="scitex-todo",
    )
    # Act
    filtered = filter_to_net_new_lines(
        _BASE_SAMPLE_LINENOS_SHIFTED, net, distribution="scitex-todo"
    )
    # Assert — none of the inherited finding lines survive.
    assert "monkeypatch" not in filtered
