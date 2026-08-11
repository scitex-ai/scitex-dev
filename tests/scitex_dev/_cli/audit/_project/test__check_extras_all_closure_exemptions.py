#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PS-221 must honour the exemption stanza its own advice tells you to write.

Reported 2026-08-10 by scitex-storage. They wrote the exact config PS-221's
remediation text prescribes:

    audit:
      exemptions:
        PS-221:
          - path: pyproject.toml
            line: 0
            reason: "..."

and measured, on BOTH auditor versions:

    0.42.0 -> "0 masked by skip-rules (0 declared)", violation still unmasked
    0.43.1 -> "0 masked by skip-rules (0 declared)", violation still unmasked

Their diagnosis was that the schema was unimplemented. It was not: the
mechanism exists in `_config/_exemptions.py`, carries a mandatory reason,
and was already wired into PS-220, PS-222 and two others. **PS-221's
checker simply never consulted it.**

So the rule's own advice sent readers to write config the rule never read —
remediation advice that does not remediate, which costs the reader more
than silence would, because they act on it and then have to discover by
experiment that the documented path is inert.

WHY THE EXEMPTION IS PINNED TO A REQUIREMENT'S LINE rather than to
`pyproject.toml` as a whole: `exemption_for` matches `(rule, path, line)`
exactly, so a whole-file entry would silence EVERY PS-221 finding in the
package at once — rule granularity wearing a per-site costume. storage
explicitly refused the rule-wide `skip_rules` for that reason: it would
have masked scitex-io's pre-existing PS-221 debt behind their own
deliberate licence decision. These tests pin that distinction.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_extras_all_closure import (
    check_ps221_extras_all_closure,
)


@dataclass
class Violation:
    rule: str
    where: str
    detail: str


PYPROJECT = """\
[project]
name = "demo-pkg"
version = "0.1.0"

[project.optional-dependencies]
pdf = ["pypdf>=4"]
pdf-fast = ["pymupdf>=1.24"]
all = ["demo-pkg[pdf]"]
"""

CONFIG = """\
audit:
  exemptions:
    PS-221:
      - path: pyproject.toml
        line: {line}
        reason: "{reason}"
"""


def _repo(tmp_path: Path, config: str | None = None) -> Path:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    if config is not None:
        cfg_dir = tmp_path / ".scitex" / "dev"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.yaml").write_text(config, encoding="utf-8")
    return tmp_path


def _run(repo: Path) -> list[Violation]:
    out: list[Violation] = []
    check_ps221_extras_all_closure(repo, Violation, out)
    return [v for v in out if v.rule == "PS-221"]


def _pymupdf_line(repo: Path) -> int:
    for idx, text in enumerate(
        (repo / "pyproject.toml").read_text(encoding="utf-8").splitlines(), 1
    ):
        if "pymupdf" in text:
            return idx
    raise AssertionError("fixture lost its pymupdf line")


class TestTheRuleStillFiresWithoutAnExemption:
    """A fix that silences everything is worse than the bug."""

    def test_the_uncovered_extra_is_reported(self, tmp_path):
        # Arrange
        repo = _repo(tmp_path)
        # Act
        found = _run(repo)
        # Assert
        assert len(found) == 1

    def test_the_report_names_the_missing_requirement(self, tmp_path):
        # Arrange
        repo = _repo(tmp_path)
        # Act
        found = _run(repo)
        # Assert
        assert "pymupdf" in found[0].detail


class TestTheDocumentedStanzaActuallySilencesIt:
    """The thing nobody verified when the advice was written."""

    def test_an_exemption_at_the_requirement_line_silences_it(self, tmp_path):
        # Arrange
        repo = _repo(tmp_path)
        line = _pymupdf_line(repo)
        repo = _repo(
            tmp_path, CONFIG.format(line=line, reason="AGPL, deliberate")
        )
        # Act
        found = _run(repo)
        # Assert
        assert found == []


class TestTheExemptionIsPinnedToOneSite:
    """Per-SITE, not per-rule. This is the whole point of the mechanism."""

    def test_a_whole_file_entry_does_not_silence_a_requirement(self, tmp_path):
        """`line: 0` must NOT blanket every PS-221 finding in the package."""
        # Arrange
        repo = _repo(tmp_path, CONFIG.format(line=0, reason="too broad"))
        # Act
        found = _run(repo)
        # Assert
        assert len(found) == 1

    def test_an_exemption_on_the_wrong_line_does_not_silence_it(self, tmp_path):
        # Arrange
        repo = _repo(tmp_path, CONFIG.format(line=1, reason="wrong site"))
        # Act
        found = _run(repo)
        # Assert
        assert len(found) == 1


class TestAReasonlessExemptionIsRefused:
    """An exemption with no stated reason is the unexamined suppression the
    mechanism exists to catch."""

    @pytest.mark.parametrize("reason", ["", "   "])
    def test_a_blank_reason_does_not_silence_the_site(self, tmp_path, reason):
        # Arrange
        repo = _repo(tmp_path)
        line = _pymupdf_line(repo)
        repo = _repo(tmp_path, CONFIG.format(line=line, reason=reason))
        # Act
        found = [v for v in _run(repo) if "pymupdf" in v.detail]
        # Assert
        assert len(found) == 1


# EOF
