# -*- coding: utf-8 -*-
"""PS-220's STAGED gate: warning by default, error once a package opts in.

`audit_project` computes `exit_code = 1 if n_errors > 0 else 0`, counting
only "E" findings. PS-220 is now registered at "W", so it must NOT fail a
build on its own — and it MUST fail one for a package that has declared
`audit.enforce-logging: {level: error, reason: ...}`. Both halves are tested
here, because a gate never observed to fail is not known to be a check, and
a gate never observed to pass is not known to be staged.

These tests run the REAL `audit_project` end-to-end against a temp package
tree (no mocks), scoped with `rules={"PS-220"}` so the exit code is driven
by PS-220 alone rather than by whatever else the auditor happens to find.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._project._audit import audit_project
from scitex_dev._cli.audit._project._registry import RULES

_DIST = "scitex-ps220-demo"

# The per-package opt-in: level + a MANDATORY written reason.
_OPT_IN = (
    "project-type:\n"
    "  - pip\n"
    "audit:\n"
    "  enforce-logging:\n"
    "    level: error\n"
    '    reason: "print migration complete; all sites on scitex-logging"\n'
)


def _build(repo: Path, body: str, config_yaml: str = "project-type:\n  - pip\n") -> Path:
    """Create a minimal src-layout package whose `_core.py` holds `body`."""
    pkg = repo / "src" / "scitex_ps220_demo"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "_core.py").write_text(body, encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "{_DIST}"\nversion = "0.0.0+local"\n',
        encoding="utf-8",
    )
    cfg = repo / ".scitex" / "dev" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(config_yaml, encoding="utf-8")
    return repo


def _audit(repo: Path) -> int:
    return audit_project(_DIST, repo=repo, json_out=True, rules={"PS-220"})


# --- the registered severity ------------------------------------------------


def test_ps220_is_registered_at_warning_severity():
    # Arrange
    # Act
    severity = RULES["PS-220"].severity
    # Assert
    assert severity == "W"


def test_ps220_noqa_deprecated_rule_is_no_longer_registered():
    # Arrange — the `# noqa` hatch and its deprecation notice are removed
    # Act
    codes = set(RULES)
    # Assert
    assert "PS-220-noqa-deprecated" not in codes


# --- staged default: a print does NOT fail the build -------------------------


def test_print_in_package_source_does_not_fail_a_non_opted_in_package(tmp_path):
    # Arrange — one bare print of human prose in shippable source
    _build(tmp_path, "def go():\n    print('hello')\n")
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


# --- opted-in package: the same print DOES fail the build --------------------


def test_print_in_package_source_fails_an_opted_in_package(tmp_path):
    # Arrange — identical source; the ONLY variable is the opt-in declaration
    _build(tmp_path, "def go():\n    print('hello')\n", config_yaml=_OPT_IN)
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 1


def test_stderr_print_fails_an_opted_in_package(tmp_path):
    # Arrange — scitex-logging owns stderr
    _build(
        tmp_path,
        "import sys\ndef go():\n    print('boom', file=sys.stderr)\n",
        config_yaml=_OPT_IN,
    )
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 1


def test_opt_in_without_a_reason_does_not_gate_the_build_on_prints(tmp_path):
    # Arrange — a reasonless opt-in is REJECTED, so it must not enforce.
    # (The rejection itself is reported at E — see the config-error test
    # below — so this asserts the rejection is what fails, not the print.)
    _build(
        tmp_path,
        "import scitex_logging as slogging\n"
        "log = slogging.getLogger(__name__)\n"
        "def go():\n    log.info('clean')\n",
        config_yaml=(
            "project-type:\n"
            "  - pip\n"
            "audit:\n"
            "  enforce-logging:\n"
            "    level: error\n"
            '    reason: "   "\n'
        ),
    )
    # Act
    code = _audit(tmp_path)
    # Assert — clean source, but the malformed declaration is a hard error
    assert code == 1


# --- and the gate PASSES when it should (control) ---------------------------


def test_clean_source_exits_zero(tmp_path):
    # Arrange — the canonical scitex-logging form
    _build(
        tmp_path,
        "import scitex_logging as slogging\n"
        "log = slogging.getLogger(__name__)\n"
        "def go():\n    log.success('done')\n",
    )
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


def test_machine_readable_stdout_payload_exits_zero(tmp_path):
    # Arrange — output IS the product; a logger would corrupt it
    _build(tmp_path, "import json\ndef go(x):\n    print(json.dumps(x))\n")
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


def test_exempted_site_with_a_reason_exits_zero_when_opted_in(tmp_path):
    # Arrange — an opted-in package whose one site carries a written exemption
    _build(
        tmp_path,
        "def go(x):\n    print(x.render())\n",
        config_yaml=(
            "project-type:\n"
            "  - pip\n"
            "audit:\n"
            "  enforce-logging:\n"
            "    level: error\n"
            '    reason: "migration complete"\n'
            "  exemptions:\n"
            "    PS-220:\n"
            "      - path: src/scitex_ps220_demo/_core.py\n"
            "        line: 2\n"
            '        reason: "renders the --json payload a shell consumes"\n'
        ),
    )
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


def test_blank_reason_exemption_fails_the_build_even_without_opt_in(tmp_path):
    # Arrange — config errors are NOT staged: a reasonless exemption is a
    # hard error regardless of the project's PS-220 severity.
    _build(
        tmp_path,
        "def go(x):\n    print(x.render())\n",
        config_yaml=(
            "project-type:\n"
            "  - pip\n"
            "audit:\n"
            "  exemptions:\n"
            "    PS-220:\n"
            "      - path: src/scitex_ps220_demo/_core.py\n"
            "        line: 2\n"
            '        reason: "  "\n'
        ),
    )
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 1


def test_research_hybrid_project_does_not_fail_the_build(tmp_path):
    # Arrange
    _build(
        tmp_path,
        "def go():\n    print('hello')\n",
        config_yaml="project-type:\n  - pip\n  - research\n",
    )
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


def test_research_hybrid_with_a_reasoned_opt_in_fails_the_build(tmp_path):
    # Arrange — a research repo that WANTS the mandate writes it down
    _build(
        tmp_path,
        "def go():\n    print('hello')\n",
        config_yaml=(
            "project-type:\n"
            "  - pip\n"
            "  - research\n"
            "audit:\n"
            "  enforce-logging:\n"
            "    level: error\n"
            '    reason: "this tree ships as a package too"\n'
        ),
    )
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 1


def test_noqa_no_longer_keeps_an_opted_in_build_green(tmp_path):
    # Arrange — the hatch is REMOVED; the print is prose, so it must fire
    _build(
        tmp_path,
        "def go():\n    print('hello')  # noqa: legacy\n",
        config_yaml=_OPT_IN,
    )
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 1


# EOF
