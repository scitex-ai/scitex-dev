# -*- coding: utf-8 -*-
"""PS-230 — retired role vocabulary in package prose.

Every test asserts one thing (STX-TQ007). The negative direction is covered
first-class: conforming prose must produce ZERO findings, and each documented
allowlist entry gets its own control case — a rule that fires on everything is
indistinguishable from a rule that fires on nothing.

The fixtures are REAL lines measured in this repo on 2026-08-11, not invented
ones: `PROTECTED_BRANCHES = {"develop", "main", "master"}` (`_sync_helpers.py`),
the ControlMaster prose in `linter/_rules/_hpc_ssh.py`, the `docs/MASTER/skills/`
legacy layout `_ecosystem/_skills/skills.py` still reads, and the `--master` /
`master_host` pair the credential-rotation skills document.

No mocks: every case writes a real `src/<pkg>/` tree under `tmp_path` and runs
the real check over it.
"""

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_naming_vocabulary import (
    NAMING_VOCABULARY_RULES,
    check_ps230_naming_vocabulary,
)
from scitex_dev._cli.audit._project._violation import Violation

# --------------------------------------------------------------------- #
# Helpers                                                                #
# --------------------------------------------------------------------- #


def _repo(tmp_path: Path, relpath: str, text: str) -> Path:
    """Write `text` at `src/<relpath>` and return the repo root."""
    target = tmp_path / "src" / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return tmp_path


def _run(repo: Path) -> list[Violation]:
    out: list[Violation] = []
    check_ps230_naming_vocabulary(repo, Violation, out)
    return [v for v in out if v.rule == "PS-230"]


# --------------------------------------------------------------------- #
# It FIRES — the rot the operator described                              #
# --------------------------------------------------------------------- #


def test_retired_word_in_docstring_is_flagged(tmp_path):
    """A retired role word in a Python docstring is reported."""
    # Arrange
    body = '"""Merge helper.\n\nThe master decides the order.\n"""\n'
    repo = _repo(tmp_path, "pkg/_merge.py", body)
    # Act
    findings = _run(repo)
    # Assert
    assert len(findings) == 1


def test_db_domain_replica_is_not_mechanically_caught(tmp_path):
    """KNOWN LIMITATION, pinned deliberately: bare `replica` never fires.

    The naming table retires `primary/replica` for DB replication (the store
    is multi-writer, so `node/origin` is the model) while making those very
    words CORRECT for credentials. A line-level rule cannot tell which domain
    a sentence belongs to, so flagging bare `replica` would fire on every
    correct credential doc. This rule therefore catches the DB-domain misuse
    NOT AT ALL — `store/_merge.py`'s stale "a replica that saw..." was found
    by reading, not by this check. Do not "fix" this test by banning the
    word; that trade was measured and refused.
    """
    # Arrange
    body = '"""A replica that saw the elements in a different order."""\n'
    repo = _repo(tmp_path, "pkg/store/_merge.py", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_retired_word_in_markdown_is_flagged(tmp_path):
    """A retired role word in a skills markdown file is reported."""
    # Arrange
    body = "# Rotation\n\nThe MASTER host is the sole refresher per account.\n"
    repo = _repo(tmp_path, "pkg/_skills/14_credentials.md", body)
    # Act
    findings = _run(repo)
    # Assert
    assert len(findings) == 1


def test_retired_word_in_comment_is_flagged(tmp_path):
    """A retired role word in a comment is reported — comments are prose."""
    # Arrange
    repo = _repo(tmp_path, "pkg/x.py", "# the slave replays the log\nX = 1\n")
    # Act
    findings = _run(repo)
    # Assert
    assert len(findings) == 1


def test_follower_in_docstring_is_flagged(tmp_path):
    """`follower` is retired — the `lead/follower` pair maps to controller/worker."""
    # Arrange
    repo = _repo(tmp_path, "pkg/x.py", '"""Each follower replays the log."""\n')
    # Act
    findings = _run(repo)
    # Assert
    assert len(findings) == 1


def test_finding_names_the_file_and_line(tmp_path):
    """The finding is actionable: it points at an exact line, not a file."""
    # Arrange
    body = "# Rotation\n\nThe MASTER host refreshes.\n"
    repo = _repo(tmp_path, "pkg/_skills/14_credentials.md", body)
    # Act
    (finding,) = _run(repo)
    # Assert
    assert finding.where.endswith("14_credentials.md:3")


def test_finding_names_the_replacement_term(tmp_path):
    """The finding names the replacement, so the author need not look it up."""
    # Arrange
    body = "# Rotation\n\nThe MASTER host refreshes.\n"
    repo = _repo(tmp_path, "pkg/_skills/14_credentials.md", body)
    # Act
    (finding,) = _run(repo)
    # Assert
    assert "primary" in finding.detail


def test_source_dest_pair_is_flagged(tmp_path):
    """The literal slashed pair IS the retired spelling."""
    # Arrange
    repo = _repo(tmp_path, "pkg/x.py", '"""Sync runs source/dest only."""\n')
    # Act
    findings = _run(repo)
    # Assert
    assert len(findings) == 1


# --------------------------------------------------------------------- #
# It STAYS QUIET — one control case per documented allowlist entry        #
# --------------------------------------------------------------------- #


def test_conforming_prose_produces_no_findings(tmp_path):
    """Prose using the decided vocabulary produces ZERO findings."""
    # Arrange
    body = "# Rotation\n\nThe PRIMARY host refreshes; REPLICA hosts pull.\n"
    repo = _repo(tmp_path, "pkg/_skills/14_credentials.md", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_ssh_control_master_is_spared(tmp_path):
    """OpenSSH's ControlMaster is a third-party API name, not our role word."""
    # Arrange
    body = '"""Disabling the control-master / control-path costs a login."""\n'
    repo = _repo(tmp_path, "pkg/_hpc_ssh.py", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_ssh_multiplexing_prose_is_spared(tmp_path):
    """"one shared master per host" is SSH multiplexing, not a role."""
    # Arrange
    body = "# Multiplex instead: one shared master per host, reused.\n"
    repo = _repo(tmp_path, "pkg/config.py", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_git_branch_master_is_spared(tmp_path):
    """git names the `master` ref; we do not get to rename it."""
    # Arrange
    body = '"""Excludes develop/main/master and the checked-out branch."""\n'
    repo = _repo(tmp_path, "pkg/_prune.py", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_legacy_docs_master_path_is_spared(tmp_path):
    """`docs/MASTER/skills/` is an on-disk path this package still reads."""
    # Arrange
    body = '"""Legacy docs: <pkg_root>/docs/MASTER/skills/"""\n'
    repo = _repo(tmp_path, "pkg/skills.py", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_published_cli_flag_is_spared(tmp_path):
    """THE carve-out: `--master` is a published CLI token, not prose.

    Renaming the word while the flag still parses `--master` would make the
    document lie about the command. Alias first, remove later.
    """
    # Arrange
    body = "```bash\nsac accounts pull-token [--master ywata-note-win]\n```\n"
    repo = _repo(tmp_path, "pkg/_skills/15_pull.md", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_wire_field_name_is_spared(tmp_path):
    """`master_host` is a live field emitted by `sac accounts mint-token`."""
    # Arrange
    body = '  "meta": {"account":"<label>","master_host":"<host>"}\n'
    repo = _repo(tmp_path, "pkg/_skills/14_credentials.md", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_line_about_the_convention_is_spared(tmp_path):
    """Prose must be able to NAME what it retired, or nothing can be recorded."""
    # Arrange
    body = "This leaf used to say MASTER; that spelling is banned now.\n"
    repo = _repo(tmp_path, "pkg/_skills/x.md", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_naming_skill_file_is_exempt(tmp_path):
    """The skill that DEFINES the table prints its own banned-synonyms column."""
    # Arrange
    body = "| Roles | controller / worker | master/slave, lead/follower |\n"
    repo = _repo(tmp_path, "pkg/_skills/25_naming-conventions.md", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_inline_marker_opts_the_line_out(tmp_path):
    """A trailing `naming-ok` marker is the per-line escape hatch."""
    # Arrange
    body = "# the master mints it  # naming-ok: third-party wording\n"
    repo = _repo(tmp_path, "pkg/x.py", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_bare_lead_is_not_flagged(tmp_path):
    """`lead` survives as an agent name and as ordinary English."""
    # Arrange
    repo = _repo(tmp_path, "pkg/x.py", '"""This leads to a lower ceiling."""\n')
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_bare_source_word_is_not_flagged(tmp_path):
    """Only the literal `source/dest` PAIR is retired, never bare `source`."""
    # Arrange
    repo = _repo(tmp_path, "pkg/x.py", '"""Read the source file and copy it."""\n')
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


# --------------------------------------------------------------------- #
# Scope — prose only, never code                                         #
# --------------------------------------------------------------------- #


def test_code_identifiers_are_not_graded(tmp_path):
    """A live contract in CODE must never be flagged by a prose rule."""
    # Arrange
    body = 'PROTECTED_BRANCHES = frozenset({"develop", "main", "master"})\n'
    repo = _repo(tmp_path, "pkg/x.py", body)
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_string_literals_are_not_graded(tmp_path):
    """A dict key / value may be a wire field — code is out of scope."""
    # Arrange
    repo = _repo(tmp_path, "pkg/x.py", 'META = {"master_host": resolve()}\n')
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_in_package_tests_subtree_is_skipped(tmp_path):
    """Non-shippable in-package subtrees are out of scope (PS-220/223 mirror)."""
    # Arrange
    repo = _repo(tmp_path, "pkg/tests/x.py", '"""The master refreshes."""\n')
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_repo_without_src_produces_nothing(tmp_path):
    """A repo with no `src/` yields nothing rather than raising."""
    # Arrange
    repo = tmp_path
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


def test_unparseable_python_does_not_raise(tmp_path):
    """A syntax error is not this rule's business — it must not crash the audit."""
    # Arrange
    repo = _repo(tmp_path, "pkg/broken.py", "def (((\n")
    # Act
    findings = _run(repo)
    # Assert
    assert findings == []


# --------------------------------------------------------------------- #
# Registration + severity                                                #
# --------------------------------------------------------------------- #


def test_rule_tuple_ships_at_warning(tmp_path):
    """PS-230 lands at W: the auditor runs fleet-wide and siblings are unswept."""
    # Arrange
    (code, _section, _message, severity, _slug) = NAMING_VOCABULARY_RULES[0]
    # Act
    shipped = (code, severity)
    # Assert
    assert shipped == ("PS-230", "W")


def test_rule_is_registered_in_corpus():
    """The co-located tuple must actually reach `RULES` (the `_patch` hazard)."""
    # Arrange
    from scitex_dev._cli.audit._project._rules import RULES

    # Act
    registered = RULES["PS-230"].severity
    # Assert
    assert registered == "W"


def test_finding_severity_reads_as_warning(tmp_path):
    """A real finding renders at W, not E — the registered severity is honoured."""
    # Arrange
    repo = _repo(tmp_path, "pkg/x.py", '"""The master refreshes it."""\n')
    # Act
    (finding,) = _run(repo)
    # Assert
    assert finding.severity == "W"


@pytest.mark.parametrize("term", ["master", "slave", "follower"])
def test_each_retired_term_is_detected(tmp_path, term):
    """Each single-word retired term is detected on its own."""
    # Arrange
    repo = _repo(tmp_path, "pkg/x.py", f'"""The {term} handles the work."""\n')
    # Act
    findings = _run(repo)
    # Assert
    assert len(findings) == 1

# EOF
