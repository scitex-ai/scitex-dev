"""Project-auditor federation preserves checks and rejects false-green loads."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project import _rules
from scitex_dev._cli.audit._project._plugins import (
    ProjectPluginError,
    load_plugins as _load_plugins,
    register_plugin_rules,
)
from scitex_dev._cli.audit._project._rules._rule import Rule
from scitex_dev._runtime_gitignore_plugin import get_plugin as _runtime_plugin
from scitex_logging._audit_plugin import get_plugin as _logging_plugin

_GROUP = "scitex_dev.audit.project"
_BUILTIN = "scitex_dev._runtime_gitignore_plugin:get_plugin"
_LOGGING = "scitex_logging._audit_plugin:get_plugin"
_RULE = ("PS-999", "§2", "External auditor rule", "E", "external-auditor")


def load_plugins(*, entry_points_iter):
    """Keep mandatory logging while isolating optional provider discovery."""
    points = tuple(entry_points_iter())
    if not any(point.value == _LOGGING for point in points):
        points += (EntryPoint(name="scitex-logging", value=_LOGGING, group=_GROUP),)
    return _load_plugins(entry_points_iter=lambda: points)


def get_plugin():
    """Expected mandatory logging and built-in runtime declarations."""
    runtime = _runtime_plugin()
    logging = _logging_plugin()
    return {
        "rules": [*logging["rules"], *runtime["rules"]],
        "checks": [*logging["checks"], *runtime["checks"]],
        "registry_checks": runtime.get("registry_checks", []),
    }


def check_external(repo, violation_class, out):
    out.append(violation_class("PS-999", str(repo), "external check ran"))


def check_other(repo, violation_class, out):
    out.append(violation_class("PS-998", str(repo), "other check ran"))


def check_registry_external(scitex_dir, violation_class, out):
    out.append(
        violation_class("PS-997", str(scitex_dir), "external registry check ran")
    )


def get_external_plugin():
    return {"rules": [_RULE], "checks": [check_external]}


def get_other_plugin():
    return {
        "rules": [("PS-998", "§2", "Other auditor rule", "W", "other-auditor")],
        "checks": [check_other],
    }


def get_duplicate_rule_plugin():
    return {"rules": [_RULE], "checks": [check_other]}


def get_duplicate_check_plugin():
    return {"rules": [], "checks": [check_external]}


def get_registry_plugin():
    return {
        "rules": [
            ("PS-997", "§4b", "External registry rule", "E", "external-registry")
        ],
        "checks": [],
        "registry_checks": [check_registry_external],
    }


def get_duplicate_registry_check_plugin():
    return {"rules": [], "checks": [], "registry_checks": [check_registry_external]}


def get_cross_scope_plugin():
    return {
        "rules": [],
        "checks": [check_other],
        "registry_checks": [check_other],
    }


def get_core_collision_plugin():
    return {
        "rules": [("PS-101", "§1", "A replacement is forbidden", "I", "collision")],
        "checks": [],
    }


def get_nonmapping_plugin():
    return []


def get_missing_rules_plugin():
    return {"checks": []}


def get_bad_rules_type_plugin():
    return {"rules": {}, "checks": []}


def get_bad_checks_type_plugin():
    return {"rules": [], "checks": None}


def get_bad_short_rule_plugin():
    return {"rules": [("PS-999", "§2")], "checks": []}


def get_bad_list_rule_plugin():
    return {"rules": [list(_RULE)], "checks": []}


def get_bad_field_plugin():
    return {"rules": [("PS-999", "§2", 7, "E", "bad")], "checks": []}


def get_bad_severity_plugin():
    return {"rules": [("PS-999", "§2", "Bad severity", "error", "bad")], "checks": []}


def get_bad_empty_code_plugin():
    return {"rules": [("", "§2", "Missing rule ID", "E", "bad")], "checks": []}


def get_bad_checker_plugin():
    return {"rules": [], "checks": [7]}


def get_bad_registry_type_plugin():
    return {"rules": [], "checks": [], "registry_checks": None}


def get_bad_registry_checker_plugin():
    return {"rules": [], "checks": [], "registry_checks": [7]}


def get_raising_plugin():
    raise ValueError("provider setup failed")


NONCALLABLE_PROVIDER = 7


def _point(provider: str, *, name: str | None = None) -> EntryPoint:
    return EntryPoint(
        name=name or provider,
        value=f"{__name__}:{provider}",
        group=_GROUP,
    )


def test_runtime_metadata_absence_still_loads_the_owner_rule():
    # Arrange
    expected = get_plugin()
    # Act
    bundle = load_plugins(entry_points_iter=lambda: ())
    # Assert
    assert (bundle.rules, bundle.checks, bundle.registry_checks) == (
        tuple(expected["rules"]),
        tuple(expected["checks"]),
        tuple(expected.get("registry_checks", ())),
    )


def test_absent_logging_provider_cannot_report_success():
    with pytest.raises(ProjectPluginError, match="mandatory scitex-logging.*absent"):
        _load_plugins(entry_points_iter=lambda: ())


def test_logging_metadata_registers_one_project_check():
    bundle = _load_plugins()
    assert [rule[0] for rule in bundle.rules].count("PS-220") == 1
    assert (
        sum(
            check.__module__ == "scitex_logging._output_auditor"
            for check in bundle.checks
        )
        == 1
    )


def test_repeated_logging_provider_is_rejected():
    point = EntryPoint(name="scitex-logging", value=_LOGGING, group=_GROUP)
    with pytest.raises(ProjectPluginError, match="duplicate provider"):
        _load_plugins(entry_points_iter=lambda: (point, point))


def test_real_self_entry_point_does_not_register_the_owner_twice():
    # Arrange
    point = EntryPoint(name="scitex-dev", value=_BUILTIN, group=_GROUP)
    expected = get_plugin()
    # Act
    bundle = load_plugins(entry_points_iter=lambda: (point,))
    # Assert
    assert (set(bundle.rules), set(bundle.checks), set(bundle.registry_checks)) == (
        set(expected["rules"]),
        set(expected["checks"]),
        set(expected.get("registry_checks", ())),
    )


def test_external_provider_joins_the_mandatory_owner():
    # Arrange
    point = _point("get_external_plugin")
    owner = get_plugin()
    # Act
    bundle = load_plugins(entry_points_iter=lambda: (point,))
    # Assert
    assert (bundle.rules, bundle.checks, bundle.registry_checks) == (
        (_RULE, *owner["rules"]),
        (check_external, *owner["checks"]),
        tuple(owner.get("registry_checks", ())),
    )


def test_optional_registry_check_is_kept_separate_from_project_checks():
    # Arrange
    point = _point("get_registry_plugin")
    owner = get_plugin()
    # Act
    bundle = load_plugins(entry_points_iter=lambda: (point,))
    # Assert
    assert (bundle.checks, bundle.registry_checks) == (
        tuple(owner["checks"]),
        (check_registry_external, *owner.get("registry_checks", ())),
    )


def test_a_callable_may_be_declared_once_in_each_scope():
    # Arrange
    point = _point("get_cross_scope_plugin")
    # Act
    bundle = load_plugins(entry_points_iter=lambda: (point,))
    # Assert
    assert (bundle.checks[0], bundle.registry_checks[0]) == (check_other, check_other)


def test_injected_discoveries_do_not_share_a_cached_result():
    # Arrange
    first_point = _point("get_external_plugin")
    second_point = _point("get_other_plugin")
    # Act
    first = load_plugins(entry_points_iter=lambda: (first_point,))
    second = load_plugins(entry_points_iter=lambda: (second_point,))
    # Assert
    assert (first.rules[0][0], second.rules[0][0]) == ("PS-999", "PS-998")


@pytest.mark.parametrize(
    ("provider", "message"),
    [
        ("NONCALLABLE_PROVIDER", "callable get_plugin"),
        ("get_nonmapping_plugin", "return a mapping"),
        ("get_missing_rules_plugin", "rules.*list or tuple"),
        ("get_bad_rules_type_plugin", "rules.*list or tuple"),
        ("get_bad_checks_type_plugin", "checks.*list or tuple"),
        ("get_bad_short_rule_plugin", "invalid five-field rule"),
        ("get_bad_list_rule_plugin", "invalid five-field rule"),
        ("get_bad_field_plugin", "invalid five-field rule"),
        ("get_bad_severity_plugin", "invalid five-field rule"),
        ("get_bad_empty_code_plugin", "invalid five-field rule"),
        ("get_bad_checker_plugin", "must be callable"),
        ("get_bad_registry_type_plugin", "registry_checks.*list or tuple"),
        ("get_bad_registry_checker_plugin", "registry_checks.*must be callable"),
        ("get_raising_plugin", "provider setup failed"),
    ],
)
def test_broken_payloads_abort_discovery_with_provider_context(provider, message):
    # Arrange
    point = _point(provider)
    # Act
    # Assert
    with pytest.raises(ProjectPluginError, match=f"{provider}.*{message}"):
        load_plugins(entry_points_iter=lambda: (point,))


def test_declared_but_unimportable_provider_is_not_skipped():
    # Arrange
    point = EntryPoint(
        name="missing-owner",
        value="missing_project_auditor_owner:get_plugin",
        group=_GROUP,
    )
    # Act
    # Assert
    with pytest.raises(ProjectPluginError, match="missing-owner.*could not load"):
        load_plugins(entry_points_iter=lambda: (point,))


@pytest.mark.parametrize(
    ("provider", "message"),
    [
        ("get_duplicate_rule_plugin", "duplicate rule 'PS-999'"),
        ("get_duplicate_check_plugin", "duplicate check"),
    ],
)
def test_duplicate_declarations_abort_discovery(provider, message):
    # Arrange
    points = (_point("get_external_plugin"), _point(provider))
    # Act
    # Assert
    with pytest.raises(ProjectPluginError, match=message):
        load_plugins(entry_points_iter=lambda: points)


def test_duplicate_registry_checks_abort_discovery():
    # Arrange
    points = (
        _point("get_registry_plugin"),
        _point("get_duplicate_registry_check_plugin"),
    )
    # Act
    # Assert
    with pytest.raises(ProjectPluginError, match="duplicate check.*registry_checks"):
        load_plugins(entry_points_iter=lambda: points)


def test_engine_rule_collision_preserves_the_existing_registry():
    # Arrange
    original = Rule("PS-101", "§1", "Engine-owned", "E", "original")
    registry = {original.code: original}
    point = _point("get_core_collision_plugin")
    bundle = load_plugins(entry_points_iter=lambda: (point,))
    failure = ""
    # Act
    try:
        register_plugin_rules(registry, Rule, plugins=bundle)
    except ProjectPluginError as exc:
        failure = str(exc)
    # Assert
    assert ("PS-101" in failure, registry) == (True, {original.code: original})


def test_plugin_rule_uses_the_existing_final_override_pass():
    # Arrange
    source = Path(_rules.__file__).read_text(encoding="utf-8")
    source = source.replace(
        "_SEVERITY_OVERRIDES: dict[str, str] = {",
        '_SEVERITY_OVERRIDES: dict[str, str] = {\n    "PS-234": "W",',
        1,
    )
    namespace = {
        "__name__": _rules.__name__,
        "__package__": _rules.__name__,
        "__file__": _rules.__file__,
    }
    # Act
    exec(compile(source, _rules.__file__, "exec"), namespace)
    # Assert
    assert namespace["RULES"]["PS-234"].severity == "W"


def test_installed_metadata_registers_and_invokes_an_external_check(tmp_path):
    # Arrange
    module = tmp_path / "external_audit_owner.py"
    module.write_text(
        "def check(repo, violation_class, out):\n"
        "    out.append(violation_class('PS-999', str(repo), 'external check ran'))\n"
        "def registry_check(root, violation_class, out):\n"
        "    out.append(violation_class('PS-997', str(root), 'registry check ran'))\n"
        "def get_plugin():\n"
        "    return {'rules': [('PS-999', '§2', 'External auditor rule', 'E', "
        "'external-auditor'), ('PS-997', '§4b', 'External registry rule', 'E', "
        "'external-registry')], 'checks': [check], 'registry_checks': [registry_check]}\n",
        encoding="utf-8",
    )
    dist = tmp_path / "external_audit_owner-0.0.1.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: external-audit-owner\nVersion: 0.0.1\n",
        encoding="utf-8",
    )
    (dist / "entry_points.txt").write_text(
        f"[{_GROUP}]\nexternal-owner = external_audit_owner:get_plugin\n",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    registry = repo / ".scitex"
    registry.mkdir()
    src = Path(__file__).resolve().parents[5] / "src"
    script = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "sys.path[:0] = [sys.argv[1], sys.argv[2]]\n"
        "from scitex_dev._cli.audit._project import RULES\n"
        "from scitex_dev._cli.audit._project._run_checks import run_checks\n"
        "import click\n"
        "from click.testing import CliRunner\n"
        "from scitex_dev._cli.ecosystem._cmds._audit_registry_layout import register\n"
        "out = []\n"
        "run_checks(Path(sys.argv[3]), 'demo', out, skip_mirror=True)\n"
        "selected = [v for v in out if v.rule in {'PS-999', 'PS-997'}]\n"
        "command = click.Group()\n"
        "register(command)\n"
        "result = CliRunner().invoke(command, ['audit-registry-layout', "
        "'--scitex-dir', str(Path(sys.argv[3]) / '.scitex'), '--json'])\n"
        "sys.stdout.write(json.dumps({\n"
        "    'registered': RULES['PS-999'].slug,\n"
        "    'findings': [(v.rule, v.where, v.detail, v.severity) for v in selected],\n"
        "    'registry_exit': result.exit_code,\n"
        "    'registry_findings': json.loads(result.output)['violations'],\n"
        "}))\n"
    )
    # Act
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(src), str(tmp_path), str(repo)],
        capture_output=True,
        text=True,
        check=True,
    )
    # Assert
    assert json.loads(result.stdout) == {
        "registered": "external-auditor",
        "findings": [["PS-999", str(repo), "external check ran", "E"]],
        "registry_exit": 1,
        "registry_findings": [
            {
                "rule": "PS-997",
                "where": str(registry),
                "detail": "registry check ran",
                "severity": "E",
            }
        ],
    }
