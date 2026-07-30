#!/usr/bin/env python3
# Timestamp: 2026-07-29
# File: tests/scitex_dev/_cli/audit/test__diff_fail_open.py

"""An ERRO the key extractor cannot parse must still be able to block.

Regression cover for the P0 in which a REQUIRED merge gate printed
error lines and exited 0. `extract_violation_keys` skipped every line
`_FINDING_RE` could not match, so those errors produced no key, could
not be net-new, and could not affect the exit code — while
`filter_to_net_new_lines` kept the same lines as framing and printed
them. The renderer and the counter disagreed by construction.

Measured 2026-07-29 on real `audit-all` output: for scitex-io, 33 ERRO
lines produced 0 keys.

The second half of this file is just as load-bearing as the first. The
obvious repair — fail open on ANY level-prefixed line — is a trap:
multi-line advisory banners carry `WARN:` on every continuation line,
and a scitex-dev run measured 432 level-prefixed lines of which 431
were banner prose. That repair would manufacture ~430 findings and
block every PR. So the WARN/INFO tests below are not padding; they pin
the boundary that keeps this fix from becoming a gate that cannot pass.
"""

from scitex_dev._cli.audit._diff import (
    UNPARSED_RULE,
    compute_net_new,
    extract_violation_keys,
    filter_to_net_new_lines,
)

# A real dropped line, verbatim from `audit-all scitex-io` (two bracket
# groups, and a PATH rather than a dist after them).
UNPARSABLE_ERRO = (
    "ERRO:   [E] [PS-221 §3 public-extra-not-closed-under-all] "
    "/home/ywatanabe/proj/scitex-io/pyproject.toml: requirement "
    "`pytest>=7.0` in PUBLIC extra"
)

# A real continuation line from the currency-gate advisory banner.
BANNER_WARN = (
    "WARN: Judge by CONTENTS, never by directory SIZE. On an overlay "
    "filesystem (any"
)

BANNER_INFO = (
    "INFO: scitex-io: cli-audit dict /home/agent/.scitex/dev/"
    "cli-audit-dict.yaml (user, via home; absent)"
)


def test_unparsable_erro_line_still_produces_a_violation_key():
    # Arrange
    stdout = UNPARSABLE_ERRO
    # Act
    keys = extract_violation_keys(stdout)
    # Assert
    assert len(keys) == 1


def test_unparsable_erro_key_is_tagged_unparsed():
    # Arrange
    stdout = UNPARSABLE_ERRO
    # Act
    keys = extract_violation_keys(stdout)
    # Assert
    assert next(iter(keys)).rule == UNPARSED_RULE


def test_advisory_warn_prose_produces_no_violation_key():
    # Arrange
    stdout = BANNER_WARN
    # Act
    keys = extract_violation_keys(stdout)
    # Assert
    assert keys == set()


def test_advisory_info_line_produces_no_violation_key():
    # Arrange
    stdout = BANNER_INFO
    # Act
    keys = extract_violation_keys(stdout)
    # Assert
    assert keys == set()


def test_a_whole_advisory_banner_produces_no_violation_key():
    # Arrange — the shape that would have blocked every PR in the fleet
    stdout = "\n".join([BANNER_WARN] * 400 + [BANNER_INFO] * 30)
    # Act
    keys = extract_violation_keys(stdout)
    # Assert
    assert keys == set()


def test_same_finding_under_a_different_checkout_root_keys_identically():
    # Arrange — HEAD and the detached baseline worktree live at
    # different absolute paths by construction.
    head = UNPARSABLE_ERRO
    base = UNPARSABLE_ERRO.replace("/home/ywatanabe/proj", "/tmp/base-wt")
    # Act
    net_new = compute_net_new(head, base)
    # Assert
    assert net_new == set()


# A real dropped line whose subject is a DIRECTORY, not a file: emitted by
# the project-structure auditor for every repo that has any findings. This
# shape is what blocked merges repo-wide until 2026-07-31.
UNPARSABLE_ERRO_DIR = (
    "ERRO: scitex-todo (/home/ywatanabe/proj/scitex-cards/.worktrees/floor): "
    "project-structure: 14 error(s), 56 warning(s), 4 info"
)


def test_same_finding_under_a_different_checkout_NAME_keys_identically():
    """The directory-path case, which the prefix-only test above cannot reach.

    `test_same_finding_under_a_different_checkout_root_keys_identically`
    varies the path PREFIX (/home/ywatanabe/proj -> /tmp/base-wt), and
    `_ABS_PATH_RE` strips prefixes correctly, so it passed throughout.

    A DIRECTORY subject has no trailing slash, so the regex leaves its LAST
    component -- and that component is the checkout NAME, which is exactly
    what differs between HEAD and the staged baseline worktree. Measured on
    scitex-cards 2026-07-31: 95 keys each side, 1 net-new, 1 disappeared,
    the pair differing only by `(floor)` vs `(base-a6be1f14)`.
    """
    # Arrange -- same finding, same counts, two worktree NAMES.
    head_root = "/home/ywatanabe/proj/scitex-cards/.worktrees/floor"
    base_root = "/home/ywatanabe/proj/scitex-cards/.worktrees/base-a6be1f14"
    base = UNPARSABLE_ERRO_DIR.replace(head_root, base_root)
    roots = (head_root, base_root)
    # Act
    net_new = compute_net_new(UNPARSABLE_ERRO_DIR, base, roots=roots)
    # Assert
    assert net_new == set()


def test_a_directory_finding_without_roots_still_differs():
    """The guard is the ROOTS, not a wider regex -- shown by its absence.

    Without the roots the two lines key apart. This pins WHY the parameter
    exists, so a later "simplification" that drops it fails here rather than
    silently restoring a repo-wide merge block.
    """
    # Arrange
    base = UNPARSABLE_ERRO_DIR.replace("/.worktrees/floor", "/.worktrees/base-abc")
    # Act
    net_new = compute_net_new(UNPARSABLE_ERRO_DIR, base)
    # Assert
    assert len(net_new) == 1


def test_two_different_files_do_not_collapse_when_roots_are_stripped():
    """Stripping roots must not cost the file-level distinction.

    The rejected alternative -- widening `_ABS_PATH_RE` to eat the final
    component -- would make these two key as one, hiding a new finding
    behind an existing one. That is the collision the unparsed key exists
    to avoid, so it is asserted rather than assumed.
    """
    # Arrange
    root = "/home/ywatanabe/proj/scitex-io"
    a = f"ERRO:   [E] [PS-221 §3 x] {root}/src/a.py: requirement `p` in PUBLIC extra"
    b = f"ERRO:   [E] [PS-221 §3 x] {root}/src/b.py: requirement `p` in PUBLIC extra"
    # Act
    keys = extract_violation_keys(f"{a}\n{b}", roots=(root,))
    # Assert
    assert len(keys) == 2


def test_two_different_unparsable_errors_do_not_collapse_into_one_key():
    # Arrange — identical for far more than 60 characters, differing
    # only at the end; a truncated excerpt would merge them.
    prefix = "ERRO:   [E] [PS-221 §3 public-extra-not-closed-under-all] p.toml: requirement "
    stdout = f"{prefix}`pytest>=7.0` in PUBLIC extra\n{prefix}`black>=24.0` in PUBLIC extra"
    # Act
    keys = extract_violation_keys(stdout)
    # Assert
    assert len(keys) == 2


def test_unparsable_erro_survives_a_distribution_filter():
    # Arrange — an unparsed line has no readable dist; "I cannot tell
    # whose this is" must not collapse into "not theirs".
    stdout = UNPARSABLE_ERRO
    # Act
    keys = extract_violation_keys(stdout, distribution_filter="scitex-io")
    # Assert
    assert len(keys) == 1


def test_pre_existing_unparsable_erro_is_not_net_new():
    # Arrange
    head = UNPARSABLE_ERRO
    base = UNPARSABLE_ERRO
    # Act
    net_new = compute_net_new(head, base)
    # Assert
    assert net_new == set()


def test_newly_introduced_unparsable_erro_is_net_new():
    # Arrange
    head = UNPARSABLE_ERRO
    base = ""
    # Act
    net_new = compute_net_new(head, base)
    # Assert
    assert len(net_new) == 1


def test_filter_keeps_a_net_new_unparsable_erro_line():
    # Arrange
    head = UNPARSABLE_ERRO
    net_new = compute_net_new(head, "")
    # Act
    rendered = filter_to_net_new_lines(head, net_new)
    # Assert
    assert UNPARSABLE_ERRO in rendered


def test_filter_drops_a_pre_existing_unparsable_erro_line():
    # Arrange — the renderer must apply the same net-new test the
    # counter now applies, or the two disagree in the other direction.
    head = UNPARSABLE_ERRO
    net_new = compute_net_new(head, UNPARSABLE_ERRO)
    # Act
    rendered = filter_to_net_new_lines(head, net_new)
    # Assert
    assert UNPARSABLE_ERRO not in rendered


def test_filter_keeps_advisory_prose_regardless_of_net_new():
    # Arrange — banners are the audit's framing, not findings.
    head = BANNER_WARN
    # Act
    rendered = filter_to_net_new_lines(head, set())
    # Assert
    assert BANNER_WARN in rendered
