# -*- coding: utf-8 -*-
"""Tests for `_check_no_print.py` (PS-220).

SciTeX code must emit human-facing messages through scitex-logging, never
the builtin `print`. This check AST-scans the shippable `src/<pkg>/**.py`
tree and flags each `print(...)` that is not provably machine-readable
stdout. Each test builds a REAL temp package tree (no mocks) then asserts
whether PS-220 fires.

The discriminator itself is unit-tested in `test__print_discriminator.py`;
these tests cover the file walk, the scope exclusions, the per-site
`audit.exemptions` surface, the removal of the `# noqa` hatch, and the
STAGED severity (warning by default; each package opts in to error via
`audit.enforce-logging` with a mandatory written reason).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._config import load_config
from scitex_dev._cli.audit._project._check_no_print import (
    check_ps220_no_print,
    resolve_ps220_severity,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str
    severity_override: str | None = None


def _write_src(repo: Path, rel: str, body: str) -> Path:
    """Write `body` to `repo/src/<rel>`, creating parent dirs."""
    target = repo / "src" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def _write_config(repo: Path, body: str) -> Path:
    """Write `repo/.scitex/dev/config.yaml`."""
    target = repo / ".scitex" / "dev" / "config.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def _codes(out: list) -> list[str]:
    return [v.rule for v in out]


def _run(repo: Path) -> list:
    out: list = []
    check_ps220_no_print(repo, _StubViolation, out)
    return out


# --- PS-220 fires (positive cases) ------------------------------------------


def test_ps220_fires_on_print_in_source(tmp_path):
    # Arrange — a bare print() in package source
    _write_src(tmp_path, "scitex_demo/_core.py", "def go():\n    print('hello')\n")
    # Act
    out = _run(tmp_path)
    # Assert
    assert "PS-220" in _codes(out)


def test_ps220_reports_one_violation_per_print(tmp_path):
    # Arrange — two print calls ⇒ two violations
    _write_src(
        tmp_path,
        "scitex_demo/_core.py",
        "def go():\n    print('a')\n    print('b')\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-220", "PS-220"]


def test_ps220_detail_points_at_the_offending_line(tmp_path):
    # Arrange
    _write_src(tmp_path, "scitex_demo/_core.py", "def go():\n    print('x')\n")
    # Act
    out = _run(tmp_path)
    # Assert — the print is on line 2
    assert out[0].where.endswith(":2")


def test_ps220_fires_on_stderr_print_in_source(tmp_path):
    # Arrange — scitex-logging owns stderr
    _write_src(
        tmp_path,
        "scitex_demo/_core.py",
        "import sys, json\ndef go(x):\n    print(json.dumps(x), file=sys.stderr)\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert "PS-220" in _codes(out)


# --- PS-220 silent (negative cases) -----------------------------------------


def test_ps220_silent_on_scitex_logging_source(tmp_path):
    # Arrange — the canonical scitex-logging form, no print
    _write_src(
        tmp_path,
        "scitex_demo/_core.py",
        "import scitex_logging as slogging\n"
        "log = slogging.getLogger(__name__)\n"
        "def go():\n    log.warning('hi')\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_ps220_silent_on_json_payload_to_stdout(tmp_path):
    # Arrange — output IS the product; a logger would corrupt it (stderr)
    _write_src(
        tmp_path,
        "scitex_demo/_cli.py",
        "import json\ndef report(results):\n    print(json.dumps(results))\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_ps220_silent_on_attribute_print(tmp_path):
    # Arrange — `logger.print(...)` is an attribute call, not the builtin
    _write_src(
        tmp_path,
        "scitex_demo/_core.py",
        "def go(logger):\n    logger.print('x')\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_ps220_excludes_in_package_scripts_examples_docs(tmp_path):
    # Arrange — prints living in non-shippable in-package subtrees
    _write_src(tmp_path, "scitex_demo/scripts/run.py", "print('script')\n")
    _write_src(tmp_path, "scitex_demo/examples/demo.py", "print('example')\n")
    _write_src(tmp_path, "scitex_demo/docs/gen.py", "print('docs')\n")
    _write_src(tmp_path, "scitex_demo/tests/helper.py", "print('test')\n")
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_ps220_still_scans_when_repo_path_contains_excluded_name(tmp_path):
    # Arrange — a checkout living under a dir literally named `scripts`.
    # Matching the ABSOLUTE path against the exclusion set silently skipped
    # every file, so the rule reported a tree it had never looked at.
    repo = tmp_path / "scripts" / "checkout"
    repo.mkdir(parents=True)
    _write_src(repo, "scitex_demo/_core.py", "def go():\n    print('hello')\n")
    # Act
    out = _run(repo)
    # Assert
    assert "PS-220" in _codes(out)


# --- per-site exemptions (reason MANDATORY) ----------------------------------


_EXEMPT_YAML = (
    "project-type:\n"
    "  - pip\n"
    "audit:\n"
    "  exemptions:\n"
    "    PS-220:\n"
    "      - path: src/scitex_demo/_cli.py\n"
    "        line: 2\n"
    "        reason: {reason}\n"
)


def test_exemption_with_a_written_reason_silences_the_site(tmp_path):
    # Arrange
    _write_src(tmp_path, "scitex_demo/_cli.py", "def go(x):\n    print(x.render())\n")
    _write_config(tmp_path, _EXEMPT_YAML.format(reason='"renders the --json payload"'))
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_exemption_with_blank_reason_does_not_silence_the_site(tmp_path):
    # Arrange — a park with no stated reason is the abandonment the rule catches
    _write_src(tmp_path, "scitex_demo/_cli.py", "def go(x):\n    print(x.render())\n")
    _write_config(tmp_path, _EXEMPT_YAML.format(reason='"   "'))
    # Act
    out = _run(tmp_path)
    # Assert — the site still fires (plus a report of the bad entry)
    assert _codes(out).count("PS-220") == 2


def test_exemption_with_blank_reason_is_reported_as_invalid(tmp_path):
    # Arrange — a rejected exemption must not read as a quiet no-op
    _write_src(tmp_path, "scitex_demo/_cli.py", "def go(x):\n    print(x.render())\n")
    _write_config(tmp_path, _EXEMPT_YAML.format(reason='"   "'))
    # Act
    out = _run(tmp_path)
    # Assert
    assert any("REJECTED" in v.detail for v in out)


def test_exemption_does_not_leak_to_a_different_line(tmp_path):
    # Arrange — the exemption names line 2; the print is on line 3
    _write_src(
        tmp_path,
        "scitex_demo/_cli.py",
        "def go(x):\n    pass\n    print(x.render())\n",
    )
    _write_config(tmp_path, _EXEMPT_YAML.format(reason='"pinned to one site"'))
    # Act
    out = _run(tmp_path)
    # Assert
    assert "PS-220" in _codes(out)


def test_exemption_does_not_leak_to_a_different_file(tmp_path):
    # Arrange — same line number, different file
    _write_src(tmp_path, "scitex_demo/_other.py", "def go(x):\n    print(x.render())\n")
    _write_config(tmp_path, _EXEMPT_YAML.format(reason='"pinned to one site"'))
    # Act
    out = _run(tmp_path)
    # Assert
    assert "PS-220" in _codes(out)


# --- the `# noqa` hatch is REMOVED ------------------------------------------


def test_noqa_no_longer_suppresses_a_flagged_print(tmp_path):
    # Arrange — the removed hatch must not silence the site any more. A sweep
    # of all 118 repos under ~/proj found ZERO users before deleting it.
    _write_src(
        tmp_path,
        "scitex_demo/_cli.py",
        "def render():\n    print('done')  # noqa: legacy hatch\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-220"]


def test_noqa_no_longer_emits_the_retired_deprecation_code(tmp_path):
    # Arrange — `PS-220-noqa-deprecated` is gone; nothing may still emit it
    _write_src(
        tmp_path,
        "scitex_demo/_cli.py",
        "def render():\n    print('done')  # noqa\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert "PS-220-noqa-deprecated" not in _codes(out)


def test_noqa_on_a_structurally_spared_print_still_reports_nothing(tmp_path):
    # Arrange — the discriminator spares this site regardless of the comment
    _write_src(
        tmp_path,
        "scitex_demo/_cli.py",
        "import json\ndef render(x):\n    print(json.dumps(x))  # noqa: legacy\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


# --- staged default: WARNING for everyone ------------------------------------


def test_pip_package_resolves_ps220_to_warning_by_default(tmp_path):
    # Arrange — the staged rollout defaults every package to warning
    _write_config(tmp_path, "project-type:\n  - pip\n")
    cfg = load_config(tmp_path)
    # Act
    severity = resolve_ps220_severity(cfg)
    # Assert
    assert severity == "W"


def test_research_hybrid_resolves_ps220_to_warning_by_default(tmp_path):
    # Arrange
    _write_config(tmp_path, "project-type:\n  - pip\n  - research\n")
    cfg = load_config(tmp_path)
    # Act
    severity = resolve_ps220_severity(cfg)
    # Assert
    assert severity == "W"


def test_default_findings_carry_no_severity_override(tmp_path):
    # Arrange — W is now the rule's registered severity, so no override needed
    _write_src(tmp_path, "scitex_demo/_core.py", "def go():\n    print('hello')\n")
    _write_config(tmp_path, "project-type:\n  - pip\n")
    # Act
    out = _run(tmp_path)
    # Assert
    assert out[0].severity_override is None


# --- opt-in to error: the reason is MANDATORY --------------------------------


_OPT_IN_YAML = (
    "project-type:\n"
    "  - pip\n"
    "audit:\n"
    "  enforce-logging:\n"
    "    level: {level}\n"
    "    reason: {reason}\n"
)


def test_opt_in_with_a_written_reason_resolves_to_error(tmp_path):
    # Arrange — the package declares its print migration complete
    _write_config(
        tmp_path,
        _OPT_IN_YAML.format(level="error", reason='"migration complete (PR #412)"'),
    )
    cfg = load_config(tmp_path)
    # Act
    severity = resolve_ps220_severity(cfg)
    # Assert
    assert severity == "E"


def test_opt_in_with_a_written_reason_stores_that_reason(tmp_path):
    # Arrange
    _write_config(
        tmp_path,
        _OPT_IN_YAML.format(level="error", reason='"migration complete (PR #412)"'),
    )
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.enforce_logging_reason == "migration complete (PR #412)"


def test_opt_in_with_blank_reason_does_not_reach_error_severity(tmp_path):
    # Arrange — a reasonless opt-in must not enforce anything
    _write_config(tmp_path, _OPT_IN_YAML.format(level="error", reason='"   "'))
    cfg = load_config(tmp_path)
    # Act
    severity = resolve_ps220_severity(cfg)
    # Assert
    assert severity == "W"


def test_opt_in_with_blank_reason_is_reported_as_a_rejected_declaration(tmp_path):
    # Arrange — a rejected opt-in must not read as a quiet no-op
    _write_src(tmp_path, "scitex_demo/_core.py", "def go():\n    print('hello')\n")
    _write_config(tmp_path, _OPT_IN_YAML.format(level="error", reason='"   "'))
    # Act
    out = _run(tmp_path)
    # Assert
    assert any("REJECTED" in v.detail for v in out)


def test_rejected_declaration_is_reported_at_error_severity(tmp_path):
    # Arrange — a malformed config is a hard error, not staged migration debt
    _write_src(tmp_path, "scitex_demo/_core.py", "def go():\n    print('hello')\n")
    _write_config(tmp_path, _OPT_IN_YAML.format(level="error", reason='"   "'))
    # Act
    out = _run(tmp_path)
    notices = [v for v in out if "REJECTED" in v.detail]
    # Assert
    assert notices[0].severity_override == "E"


def test_bare_error_shorthand_is_rejected_for_carrying_no_reason(tmp_path):
    # Arrange — the pre-staging spelling `enforce-logging: error` has no reason
    _write_config(tmp_path, "project-type:\n  - pip\naudit:\n  enforce-logging: error\n")
    cfg = load_config(tmp_path)
    # Act
    severity = resolve_ps220_severity(cfg)
    # Assert
    assert severity == "W"


def test_bare_error_shorthand_records_a_rejection_notice(tmp_path):
    # Arrange
    _write_config(tmp_path, "project-type:\n  - pip\naudit:\n  enforce-logging: error\n")
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert any("REJECTED" in n for n in cfg.enforce_logging_errors)


def test_yaml_boolean_true_shorthand_is_rejected_for_carrying_no_reason(tmp_path):
    # Arrange — bare `on`/`yes` is YAML 1.1 boolean True, i.e. `error`
    _write_config(tmp_path, "project-type:\n  - pip\naudit:\n  enforce-logging: on\n")
    cfg = load_config(tmp_path)
    # Act
    severity = resolve_ps220_severity(cfg)
    # Assert
    assert severity == "W"


# --- `off` also demands a reason ---------------------------------------------


def test_off_with_a_written_reason_stops_the_rule_firing(tmp_path):
    # Arrange
    _write_src(tmp_path, "scitex_demo/_core.py", "def go():\n    print('hello')\n")
    _write_config(
        tmp_path, _OPT_IN_YAML.format(level="off", reason='"vendored third-party tree"')
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_quoted_off_level_with_a_reason_behaves_like_the_bare_one(tmp_path):
    # Arrange — YAML 1.1 turns bare `off` into False; both spellings must match
    _write_src(tmp_path, "scitex_demo/_core.py", "def go():\n    print('hello')\n")
    _write_config(
        tmp_path,
        _OPT_IN_YAML.format(level='"off"', reason='"vendored third-party tree"'),
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert out == []


def test_bare_off_shorthand_is_rejected_and_the_rule_still_fires(tmp_path):
    # Arrange — the strongest suppression available must never be reasonless
    _write_src(tmp_path, "scitex_demo/_core.py", "def go():\n    print('hello')\n")
    _write_config(tmp_path, "project-type:\n  - pip\naudit:\n  enforce-logging: off\n")
    # Act
    out = _run(tmp_path)
    # Assert
    assert "PS-220" in _codes(out)


# --- `warning` needs no reason (it IS the default) ---------------------------


def test_bare_warning_shorthand_is_accepted_without_a_reason(tmp_path):
    # Arrange — writing the default changes nothing, so it needs no rationale
    _write_config(
        tmp_path, "project-type:\n  - pip\naudit:\n  enforce-logging: warning\n"
    )
    cfg = load_config(tmp_path)
    # Act
    severity = resolve_ps220_severity(cfg)
    # Assert
    assert severity == "W"


def test_bare_warning_shorthand_records_no_rejection_notice(tmp_path):
    # Arrange
    _write_config(
        tmp_path, "project-type:\n  - pip\naudit:\n  enforce-logging: warning\n"
    )
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.enforce_logging_errors == ()


def test_unrecognised_enforce_logging_value_falls_back_to_the_staged_default(tmp_path):
    # Arrange — a typo must not silently change the gate in either direction
    _write_config(tmp_path, "project-type:\n  - pip\naudit:\n  enforce-logging: maybe\n")
    cfg = load_config(tmp_path)
    # Act
    severity = resolve_ps220_severity(cfg)
    # Assert
    assert severity == "W"


def test_unrecognised_enforce_logging_value_records_a_rejection_notice(tmp_path):
    # Arrange — falling back must be LOUD, not silent
    _write_config(tmp_path, "project-type:\n  - pip\naudit:\n  enforce-logging: maybe\n")
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert any("not a recognised level" in n for n in cfg.enforce_logging_errors)


def test_mapping_without_a_level_is_rejected(tmp_path):
    # Arrange — a reason with no level declares nothing
    _write_config(
        tmp_path,
        "project-type:\n  - pip\naudit:\n  enforce-logging:\n    reason: \"we tried\"\n",
    )
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert any("missing `level`" in n for n in cfg.enforce_logging_errors)


# EOF
