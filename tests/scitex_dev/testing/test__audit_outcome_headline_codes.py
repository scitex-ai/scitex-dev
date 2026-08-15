#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The FIRST line of a failing audit gate must name the rules that fired.

pytest's `short test summary info` is one line per failure, and it is what
CI notifications and `gh pr checks` triage are built from. While that line
read

    AssertionError: audit-all reported violations for 'sac' (exit=1).

it was a CONSTANT — byte-identical for every rule in the corpus — so two
unrelated failures were indistinguishable without downloading each job log.

Measured 2026-08-12 on scitex-agent-container (scitex-dev#593): seventeen
PRs red, all showing that one sentence, escalated as a P1 fleet-wide CI
outage and given two published root causes before anyone opened a raw log.
The real causes were four DIFFERENT rules — `PS-140` twice (different new
modules), `PS-207`, `SK-302` — each PR-local and each a one-line fix by its
own author. `audit-all` on develop exited 0 the whole time.

The rule codes were already in the captured output, four screens down.
These tests pin them onto line one.

Every finding line quoted here is VERBATIM from a real `audit-all` run
against a checkout carrying deliberately planted violations (an orphan
skill leaf and an empty test mirror dir), captured 2026-08-12.
"""

from __future__ import annotations

from scitex_dev.testing._audit_outcome import (
    _MAX_HEADLINE_CODES,
    classify_audit_outcome,
    headline_codes,
    rule_code,
    rule_codes,
    violations_message,
)


#: Canonical shape — level word, then the rule token. Warn-tier, and
#: gate-failing: `audit-skills` exits non-zero on ANY finding.
SK302 = (
    "WARN:   [SK-302 §3 leaf-not-linked-from-skill-md] "
    "/repo/src/scitex_dev/_skills/scitex-dev/99_probe-orphan-leaf.md: "
    "leaf is not referenced from `SKILL.md`"
)

#: Same file, second rule — proves one file can contribute two codes.
SK701 = (
    "WARN:   [SK-701 §FM frontmatter-missing] "
    "/repo/src/scitex_dev/_skills/scitex-dev/99_probe-orphan-leaf.md: "
    "no `---` frontmatter block"
)

#: LEGACY shape from audit-summary: a bare `[E]` severity marker sits in
#: front of the rule token. The naive "first bracket wins" reading of this
#: line yields `E`, which would name every error-tier finding in the corpus
#: identically — reintroducing the exact defect, one severity tier down.
PS207 = (
    "ERRO:   [E] [PS-207 §2 empty-test-dir] /repo/tests/scitex_dev/_probe: "
    "empty test directory mirrors /repo/src/scitex_dev/_probe (1 src files) "
    "— move corresponding test_*.py files in or remove the dir."
)

#: audit-cli reports by SECTION, not by a `XX-nnn` id. The bracket carries
#: no digit-bearing prefix at all, only `§1f`.
CLI_SECTION = (
    "WARN:   [§1f] scitex-dev dev secret set: non-canonical verb synonym "
    "'set' — use update (use `set` only for single-key config writes)"
)

#: Framing, not a finding. Present on every run, clean ones included.
BANNER = "INFO: scitex-dev: auditing /repo (branch develop, HEAD 41630140)"


class TestRuleCode:
    """One line in, one rule id out — or an honest None."""

    def test_the_canonical_shape_yields_its_rule_id(self):
        # Arrange
        line = SK302
        # Act
        code = rule_code(line)
        # Assert
        assert code == "SK-302"

    def test_the_legacy_severity_marker_is_stepped_over(self):
        """`[E] [PS-207 ...]` is PS-207, never E."""
        # Arrange
        line = PS207
        # Act
        code = rule_code(line)
        # Assert
        assert code == "PS-207"

    def test_a_section_only_token_is_still_a_code(self):
        """audit-cli names sections; `§1f` identifies the rule as well as
        `PS-207` does, and dropping it would leave a whole auditor unnamed."""
        # Arrange
        line = CLI_SECTION
        # Act
        code = rule_code(line)
        # Assert
        assert code == "§1f"

    def test_a_banner_has_no_rule_id(self):
        # Arrange
        line = BANNER
        # Act
        code = rule_code(line)
        # Assert
        assert code is None

    def test_colour_codes_do_not_hide_the_rule_id(self):
        """scitex-logging colours console output; the gate reads it anyway."""
        # Arrange
        line = f"\x1b[33m{SK302}\x1b[0m"
        # Act
        code = rule_code(line)
        # Assert
        assert code == "SK-302"

    def test_a_finding_shaped_line_with_no_rule_id_is_none(self):
        """UNKNOWN, not a rule. It must not be rendered as if it named one."""
        # Arrange
        line = "ERRO:   [something] /repo/a.py: unattributable"
        # Act
        code = rule_code(line)
        # Assert
        assert code is None


class TestRuleCodes:
    """The set, across a whole run."""

    def test_every_distinct_rule_is_named(self):
        # Arrange
        findings = [SK302, SK701, PS207]
        # Act
        codes = rule_codes(findings)
        # Assert
        assert codes == ["PS-207", "SK-302", "SK-701"]

    def test_the_same_rule_firing_four_times_is_named_once(self):
        """`PS-140` on four modules is ONE thing to go fix."""
        # Arrange
        findings = [SK302, SK302, SK302, SK302]
        # Act
        codes = rule_codes(findings)
        # Assert
        assert codes == ["SK-302"]

    def test_the_order_does_not_depend_on_which_auditor_finished_first(self):
        """audit-all fans out across a thread pool, so output order is a
        race. Two runs of the same failure must produce the same string."""
        # Arrange
        forward = rule_codes([SK302, SK701, PS207])
        # Act
        backward = rule_codes([PS207, SK701, SK302])
        # Assert
        assert forward == backward

    def test_a_run_with_no_findings_names_nothing(self):
        # Arrange
        findings: list[str] = []
        # Act
        codes = rule_codes(findings)
        # Assert
        assert codes == []


class TestHeadlineCodes:
    """The suffix that turns a constant sentence into a diagnosis."""

    def test_the_codes_are_rendered_as_a_readable_list(self):
        # Arrange
        findings = [SK302, PS207]
        # Act
        suffix = headline_codes(findings)
        # Assert
        assert suffix == ": PS-207, SK-302"

    def test_a_long_list_is_truncated_rather_than_dropped(self):
        """Knowing six of nine fired beats being shown none of them."""
        # Arrange
        findings = [
            f"WARN:   [PS-{100 + n} §2 rule-{n}] /repo/a.py: finding"
            for n in range(_MAX_HEADLINE_CODES + 3)
        ]
        # Act
        suffix = headline_codes(findings)
        # Assert
        assert suffix.endswith("(+3 more)")

    def test_the_truncated_list_spends_its_whole_budget(self):
        """Truncation drops the tail, not the budget: the last code that
        fits is shown, and the first one over it is not."""
        # Arrange
        findings = [
            f"WARN:   [PS-{100 + n} §2 rule-{n}] /repo/a.py: finding"
            for n in range(_MAX_HEADLINE_CODES + 3)
        ]
        last_shown = f"PS-{100 + _MAX_HEADLINE_CODES - 1}"
        first_elided = f"PS-{100 + _MAX_HEADLINE_CODES}"
        # Act
        suffix = headline_codes(findings)
        # Assert
        assert last_shown in suffix and first_elided not in suffix

    def test_no_attributable_finding_says_so_instead_of_going_quiet(self):
        """An empty suffix is indistinguishable from the old constant."""
        # Arrange
        findings: list[str] = []
        # Act
        suffix = headline_codes(findings)
        # Assert
        assert "no rule-attributable finding line" in suffix


class TestTheFirstLine:
    """What pytest's short summary actually carries."""

    def test_the_first_line_names_the_rules(self):
        # Arrange
        findings = [SK302, PS207]
        # Act
        message = violations_message("sac", "scitex-dev ...", 1, findings, "")
        # Assert
        assert message.splitlines()[0] == (
            "audit-all reported violations for 'sac' (exit=1): PS-207, SK-302"
        )

    def test_two_different_failures_no_longer_read_identically(self):
        """The property the whole change exists for."""
        # Arrange
        one = violations_message("sac", "cmd", 1, [PS207], "").splitlines()[0]
        # Act
        other = violations_message("sac", "cmd", 1, [SK302], "").splitlines()[0]
        # Assert
        assert one != other

    def test_the_detail_below_is_not_replaced_by_the_summary(self):
        """A summary was ADDED; the digest and its warn-tier note stay."""
        # Arrange
        findings = [SK302, PS207]
        # Act
        message = violations_message("sac", "cmd", 1, findings, "")
        # Assert
        assert "2 finding line(s) drove the failure" in message

    def test_the_full_finding_text_still_follows(self):
        # Arrange
        findings = [SK302, PS207]
        # Act
        message = violations_message("sac", "cmd", 1, findings, "")
        # Assert
        assert "leaf is not referenced from `SKILL.md`" in message

    def test_a_real_multi_auditor_run_names_all_three_rules(self):
        """End to end from captured `audit-all` output, not a hand-built list."""
        # Arrange
        output = "\n".join([BANNER, CLI_SECTION, SK302, SK701, PS207])
        _verdict, findings = classify_audit_outcome(1, output)
        # Act
        first = violations_message("scitex-dev", "cmd", 1, findings, "").splitlines()[0]
        # Assert
        assert first.endswith("(exit=1): PS-207, SK-302, SK-701, §1f")


# EOF
