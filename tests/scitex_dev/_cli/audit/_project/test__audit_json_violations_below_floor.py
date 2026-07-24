# -*- coding: utf-8 -*-
"""`audit_project --json` must not silently drop below-floor findings.

The residual half of the defect PR #417 fixed on the HUMAN path. #417
made the summary COUNTS derive from every surviving finding rather than
from `visible` (the severity-FLOOR-filtered list), so a W-only tree no
longer prints `SUCC` at the default `error` floor. But the `--json`
branch still built its `violations` list from `visible`: at the default
floor a tree of live W findings emitted `"violations": []` while
`warnings` reported a positive count. A `--json` mutation proof written
at the DEFAULT floor therefore read an empty list and could not fail —
byte-identical to a clean tree — which is exactly the shape #417 set out
to kill, left behind on the machine path.

CHOSEN SHAPE (stated so a reader knows what these tests pin): `violations`
stays FLOOR-FILTERED so `--json` keeps honouring `--severity` exactly as
the human per-finding list does, and a new `violations_total` carries
EVERY surviving finding with its severity — below-floor ones included —
so nothing is silently omitted and a consumer can filter for itself. This
matches #417's own split: the LIST respects the floor, the DISCLOSURE
(counts, and now a complete list) covers everything.

The two arms below are a matched pair. `violations_total` non-empty at
the DEFAULT floor is void without the control arm — `violations`
filtered to `[]` at the default floor — because "always emit everything"
would satisfy the first while destroying the floor's meaning. The
`severity=warning` arm pins that the floor still selects.

These read the JSON on stdout via `capfd` (the payload genuinely goes
through `click.echo`), scoped to `rules={"PS-220"}` so the finding set is
one known W rule.
"""

from __future__ import annotations

import json
from pathlib import Path

# Imported for its side effect of binding `_emit`'s SciTeXLogger before any
# stdlib `getLogger("scitex_dev.audit")` can shadow it — see the detailed
# account in test__audit_summary_counts.py.
from scitex_dev._cli.audit import _emit as _emit_module  # noqa: F401
from scitex_dev._cli.audit._project import _check_no_print
from scitex_dev._cli.audit._project._audit import audit_project

_DIST = "scitex-json-floor-demo"
_SOURCE_WITH_BARE_PRINT = "def go():\n    print('hello')\n"
_DEFAULT_CONFIG = "project-type:\n  - pip\n"


def _build(repo: Path) -> Path:
    """A minimal src-layout package whose `_core.py` holds one bare print."""
    pkg = repo / "src" / "scitex_json_floor_demo"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "_core.py").write_text(_SOURCE_WITH_BARE_PRINT, encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "{_DIST}"\nversion = "0.0.0+local"\n',
        encoding="utf-8",
    )
    cfg = repo / ".scitex" / "dev" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    return repo


def _payload(captured: str) -> dict:
    start = captured.index("{")
    end = captured.rindex("}") + 1
    return json.loads(captured[start:end])


def _audit_json(repo: Path, capfd, *, severity: str) -> dict:
    audit_project(
        _DIST, repo=repo, json_out=True, rules={"PS-220"}, severity=severity
    )
    return _payload(capfd.readouterr().out)


# --- premise guard ----------------------------------------------------------


def test_ps220_default_severity_is_w():
    # Arrange — the whole defect rests on PS-220 being a W rule that sits
    # below the default `error` floor; fail loudly if that ever changes.
    # Act
    # Assert
    assert _check_no_print._DEFAULT_SEVERITY == "W"


# --- the defect: below-floor findings must not be silently omitted ----------


def test_default_floor_json_discloses_the_warning_finding(tmp_path, capfd):
    # Arrange — one bare print (W), audited at the DEFAULT `error` floor
    repo = _build(tmp_path)
    # Act
    payload = _audit_json(repo, capfd, severity="error")
    # Assert — the residual defect emitted [] here; the complete list carries it
    rules = [v["rule"] for v in payload["violations_total"]]
    assert rules == ["PS-220"]


def test_default_floor_json_total_list_is_not_empty(tmp_path, capfd):
    # Arrange
    repo = _build(tmp_path)
    # Act
    payload = _audit_json(repo, capfd, severity="error")
    # Assert — the one-line statement of the defect
    assert payload["violations_total"] != []


def test_default_floor_total_list_carries_the_severity(tmp_path, capfd):
    # Arrange — a consumer filters on this; it must be present
    repo = _build(tmp_path)
    # Act
    payload = _audit_json(repo, capfd, severity="error")
    # Assert
    assert payload["violations_total"][0]["severity"] == "W"


def test_default_floor_total_list_is_consistent_with_the_warning_count(
    tmp_path, capfd
):
    # Arrange — the invariant that ties the new list to #417's counts
    repo = _build(tmp_path)
    # Act
    payload = _audit_json(repo, capfd, severity="error")
    # Assert
    n_w = len([v for v in payload["violations_total"] if v["severity"] == "W"])
    assert n_w == payload["warnings"]


# --- control arm: the floor still means something ---------------------------


def test_default_floor_json_violations_list_respects_the_floor(tmp_path, capfd):
    # Arrange — CONTROL ARM. Without this, "always emit everything" passes
    # the disclosure test above while silently destroying `--severity`.
    repo = _build(tmp_path)
    # Act
    payload = _audit_json(repo, capfd, severity="error")
    # Assert — a W finding is BELOW the default `error` floor, so the
    # floor-filtered list is empty; only `violations_total` carries it.
    assert payload["violations"] == []


def test_warning_floor_json_lists_the_warning_finding(tmp_path, capfd):
    # Arrange — at the `warning` floor the same W finding IS at/above the
    # floor, so the filtered list selects it. Unchanged behaviour.
    repo = _build(tmp_path)
    # Act
    payload = _audit_json(repo, capfd, severity="warning")
    # Assert
    assert [v["rule"] for v in payload["violations"]] == ["PS-220"]


# --- exit code is identical across floors -----------------------------------


def test_exit_code_is_zero_and_identical_across_floors(tmp_path, capfd):
    # Arrange — W never blocks; the floor changes what is LISTED, not the code
    repo = _build(tmp_path)
    # Act
    default_payload = _audit_json(repo, capfd, severity="error")
    warning_payload = _audit_json(repo, capfd, severity="warning")
    # Assert
    assert default_payload["exit_code"] == warning_payload["exit_code"] == 0


# EOF
