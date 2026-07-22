# -*- coding: utf-8 -*-
"""PS-220 at severity E must actually drive a NON-ZERO exit code.

This is the exact property that was missing. PS-220 shipped at "W" in its
own rule tuple, and `audit_project` computes
`exit_code = 1 if n_errors > 0 else 0` counting only "E" findings — so the
rule could never fail a build. Worse, the default severity floor is "error"
(`_audit.py:81,219-221`), so its findings were not even PRINTED unless
someone passed `--severity warning`. A rule that has never been observed to
fail is not known to be a check.

These tests run the REAL `audit_project` end-to-end against a temp package
tree (no mocks), scoped with `rules={"PS-220"}` so the exit code is driven
by PS-220 alone rather than by whatever else the auditor happens to find.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._project._audit import audit_project
from scitex_dev._cli.audit._project._registry import RULES

_DIST = "scitex-ps220-demo"


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


def test_ps220_is_registered_at_error_severity():
    # Arrange
    # Act
    severity = RULES["PS-220"].severity
    # Assert
    assert severity == "E"


# --- the gate actually fails ------------------------------------------------


def test_print_in_package_source_drives_nonzero_exit(tmp_path):
    # Arrange — one bare print of human prose in shippable source
    _build(tmp_path, "def go():\n    print('hello')\n")
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 1


def test_stderr_print_drives_nonzero_exit(tmp_path):
    # Arrange — scitex-logging owns stderr
    _build(
        tmp_path,
        "import sys\ndef go():\n    print('boom', file=sys.stderr)\n",
    )
    # Act
    code = _audit(tmp_path)
    # Assert
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


def test_exempted_site_with_a_reason_exits_zero(tmp_path):
    # Arrange — a per-site exemption carrying a written reason
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
            '        reason: "renders the --json payload a shell consumes"\n'
        ),
    )
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


def test_research_hybrid_project_does_not_fail_the_build(tmp_path):
    # Arrange — the operator has NOT ruled on research trees, so the
    # conservative default surfaces the debt instead of wedging a publish.
    _build(
        tmp_path,
        "def go():\n    print('hello')\n",
        config_yaml="project-type:\n  - pip\n  - research\n",
    )
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


def test_research_hybrid_with_explicit_enforcement_fails_the_build(tmp_path):
    # Arrange — a research repo that WANTS the mandate writes it down
    _build(
        tmp_path,
        "def go():\n    print('hello')\n",
        config_yaml=(
            "project-type:\n  - pip\n  - research\naudit:\n  enforce-logging: error\n"
        ),
    )
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 1


def test_noqa_hatch_site_does_not_fail_the_build(tmp_path):
    # Arrange — the deprecated hatch keeps working for one release. The
    # payload is prose, so the discriminator WOULD flag it: the noqa is what
    # keeps the build green here, not the carve-out.
    _build(tmp_path, "def go():\n    print('hello')  # noqa: legacy\n")
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


# EOF
