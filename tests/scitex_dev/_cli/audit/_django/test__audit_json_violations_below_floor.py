# -*- coding: utf-8 -*-
"""`audit_django --json` must not silently drop below-floor findings.

The Django sibling of the residual defect. #420 fixed `audit_django`'s
human summary the way #417 fixed `audit_project`'s, but its `--json`
branch still built `violations` from `visible` (the severity-FLOOR
filter). At the default `error` floor a tree of live W findings emitted
`"violations": []` while `warnings` reported a positive count, so a
`--json` mutation proof written at the default floor read an empty list
and could not fail.

CHOSEN SHAPE: `violations` stays FLOOR-FILTERED so `--json` still honours
`--severity`; a new `violations_total` carries EVERY surviving finding
with its severity, below-floor ones included. Identical to the fix on
`audit_project` — see that suite's docstring.

The DJ rules carry fixed severities, so the W finding here is DJ-107
(missing asgi/wsgi), scoped `rules={"DJ-107"}` so the finding set is one
known W rule. Reads the JSON on stdout via `capfd`.
"""

from __future__ import annotations

import json
from pathlib import Path

# Bind `_emit`'s SciTeXLogger before a stdlib getLogger can shadow it —
# see test__audit_summary_counts.py for the full account.
from scitex_dev._cli.audit import _emit as _emit_module  # noqa: F401
from scitex_dev._cli.audit._project import _check_no_print
from scitex_dev._cli.audit._django._audit import audit_django

_DIST = "scitex-django-json-floor-demo"

_MANAGE_PY = (
    "import os\n"
    'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n'
)


def _build(repo: Path) -> Path:
    """A Django tree missing asgi/wsgi — the single DJ-107 (W) finding."""
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "manage.py").write_text(_MANAGE_PY, encoding="utf-8")
    config = repo / "config"
    config.mkdir(exist_ok=True)
    (config / "__init__.py").write_text("", encoding="utf-8")
    (config / "urls.py").write_text("urlpatterns = []\n", encoding="utf-8")
    settings = config / "settings"
    settings.mkdir(exist_ok=True)
    (settings / "__init__.py").write_text(
        "from .settings_dev import *\n", encoding="utf-8"
    )
    for name in ("settings_shared", "settings_dev", "settings_prod"):
        (settings / f"{name}.py").write_text("", encoding="utf-8")
    # NO asgi/wsgi -> single DJ-107 (W) finding
    return repo


def _payload(captured: str) -> dict:
    start = captured.index("{")
    end = captured.rindex("}") + 1
    return json.loads(captured[start:end])


def _audit_json(repo: Path, capfd, *, severity: str) -> dict:
    audit_django(
        _DIST, repo=repo, json_out=True, rules={"DJ-107"}, severity=severity
    )
    return _payload(capfd.readouterr().out)


# --- premise guard ----------------------------------------------------------


def test_ps220_default_severity_is_w():
    # Arrange — the class of defect rests on W sitting below the default
    # `error` floor; fail loudly if the shared default ever changes.
    # Act
    # Assert
    assert _check_no_print._DEFAULT_SEVERITY == "W"


# --- the defect: below-floor findings must not be silently omitted ----------


def test_default_floor_json_discloses_the_warning_finding(tmp_path, capfd):
    # Arrange — one missing-asgi/wsgi (W), audited at the DEFAULT `error` floor
    repo = _build(tmp_path)
    # Act
    payload = _audit_json(repo, capfd, severity="error")
    # Assert — the residual defect emitted [] here; the complete list carries it
    assert [v["rule"] for v in payload["violations_total"]] == ["DJ-107"]


def test_default_floor_json_total_list_is_not_empty(tmp_path, capfd):
    # Arrange
    repo = _build(tmp_path)
    # Act
    payload = _audit_json(repo, capfd, severity="error")
    # Assert
    assert payload["violations_total"] != []


def test_default_floor_total_list_is_consistent_with_the_warning_count(
    tmp_path, capfd
):
    # Arrange
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
    # Assert — DJ-107 (W) is below the default `error` floor
    assert payload["violations"] == []


def test_warning_floor_json_lists_the_warning_finding(tmp_path, capfd):
    # Arrange — at the `warning` floor the W finding is at/above the floor
    repo = _build(tmp_path)
    # Act
    payload = _audit_json(repo, capfd, severity="warning")
    # Assert
    assert [v["rule"] for v in payload["violations"]] == ["DJ-107"]


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
