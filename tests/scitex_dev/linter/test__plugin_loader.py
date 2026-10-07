"""Installed and injected linter providers preserve mandatory coverage."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points

import pytest

from scitex_dev.linter import _plugin_loader
from scitex_dev.linter.checker import Issue, lint_source
from scitex_dev.linter.config import LinterConfig
from scitex_dev.linter.spi import Rule

GROUP = "scitex_dev.linter.plugins"
LOGGING = EntryPoint(
    name="scitex-logging", value="scitex_logging._linter_plugin:get_plugin", group=GROUP
)


@pytest.fixture(autouse=True)
def reset_cache():
    _plugin_loader.reset()
    yield
    _plugin_loader.reset()


@pytest.fixture
def restore_environ():
    saved = dict(os.environ)
    yield os.environ
    os.environ.clear()
    os.environ.update(saved)


@dataclass
class Provider:
    name: str
    payload: object

    @property
    def value(self):
        return f"test_{self.name}:get_plugin"

    def load(self):
        return lambda: self.payload


def discover(*providers):
    return _plugin_loader.load_plugins(entry_points_iter=lambda: (*providers, LOGGING))


def rule(identifier="TEST-1", category="io"):
    return Rule(identifier, "error", category, "Test rule", "Fix test rule")


class LegacyChecker:
    category = "test"

    def __init__(self, lines, config):
        self.issues = []
        self.config = config

    def visit(self, tree):
        assert self.config is not None


class ContextChecker(LegacyChecker):
    accepts_filepath = True

    def __init__(self, lines, config, *, filepath):
        super().__init__(lines, config)
        self.filepath = filepath

    def visit(self, tree):
        self.issues.append(Issue(rule(), 1, 0, self.filepath))


class BrokenChecker(LegacyChecker):
    def visit(self, tree):
        raise ValueError("checker coverage unavailable")


class BrokenProvider:
    name = "broken-owner"
    value = "broken_owner:get_plugin"

    def load(self):
        raise ModuleNotFoundError("missing owner backend")


def test_installed_metadata_has_one_logging_owner():
    points = entry_points(group=GROUP)
    owned = [ep for ep in points if ep.value == LOGGING.value]
    assert [(ep.name, ep.dist.metadata["Name"]) for ep in owned] == [
        ("scitex-logging", "scitex-logging")
    ]


def test_payload_preserves_existing_keys_and_cached_identity():
    first = _plugin_loader.load_plugins()
    assert {"rules", "call_rules", "axes_hints", "checkers"}.issubset(first)
    assert first is _plugin_loader.load_plugins()
    assert first["rules"]["PS-220"].severity == "error"


@pytest.mark.parametrize("quiet", ["", "1"])
def test_missing_provider_is_a_failure_even_when_quiet(restore_environ, quiet):
    restore_environ["SCITEX_DEV_LINTER_QUIET"] = quiet
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="mandatory scitex-logging.*absent"
    ):
        _plugin_loader.load_plugins(entry_points_iter=lambda: ())


@pytest.mark.parametrize("quiet", ["", "1"])
def test_broken_provider_is_a_failure_even_when_quiet(restore_environ, quiet):
    restore_environ["SCITEX_DEV_LINTER_QUIET"] = quiet
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="broken-owner.*missing owner backend"
    ):
        discover(BrokenProvider())
    assert _plugin_loader._cache is None


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"rules": {}},
        {"checkers": [7]},
        {"axes_hints": []},
        {"call_rules": []},
        {"rules": [object()]},
    ],
)
def test_malformed_payload_aborts_loading(payload):
    with pytest.raises(_plugin_loader.LinterPluginError, match="bad-owner"):
        discover(Provider("bad-owner", payload))


def test_duplicate_provider_is_rejected():
    provider = Provider("owner", {"rules": [rule()]})
    with pytest.raises(_plugin_loader.LinterPluginError, match="duplicate provider"):
        discover(provider, provider)


def test_duplicate_rule_ids_are_rejected():
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="duplicate rule 'TEST-1'"
    ):
        discover(
            Provider("first", {"rules": [rule()]}),
            Provider("second", {"rules": [rule()]}),
        )


def test_foreign_logging_rule_ownership_is_rejected():
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="PS-220 belongs to scitex-logging"
    ):
        discover(Provider("foreign", {"rules": [rule("PS-220")]}))


def test_duplicate_checker_objects_are_rejected():
    with pytest.raises(_plugin_loader.LinterPluginError, match="duplicate checker"):
        discover(Provider("first", {"checkers": [LegacyChecker, LegacyChecker]}))


def test_distinct_factory_bound_classes_can_share_a_lexical_name():
    def factory():
        class Bound(LegacyChecker):
            pass

        return Bound

    classes = [factory(), factory()]
    payload = discover(Provider("factory", {"checkers": classes}))
    assert all(checker in payload["checkers"] for checker in classes)


def test_parallel_call_concerns_are_grouped_without_overwriting_compatibility_view():
    first, second = rule("TEST-1"), rule("TEST-2", "figure")
    payload = discover(
        Provider(
            "a-first", {"rules": [first], "call_rules": {(None, "savefig"): first}}
        ),
        Provider(
            "b-second", {"rules": [second], "call_rules": {(None, "savefig"): second}}
        ),
    )
    assert payload["call_rules"][(None, "savefig")] is first
    assert payload["call_rule_groups"][(None, "savefig")] == (first, second)


def test_contradictory_mapping_metadata_is_rejected():
    declared = rule()
    incompatible = Rule(declared.id, "warning", "io", "Different", "Different")
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="contradictory rule 'TEST-1'"
    ):
        discover(
            Provider(
                "owner",
                {"rules": [declared], "call_rules": {(None, "savefig"): incompatible}},
            )
        )


def test_existing_two_argument_checker_and_opted_filepath_checker_both_run():
    issues = lint_source(
        "x = 1\n",
        filepath="src/demo/core.py",
        plugins={"checkers": [LegacyChecker, ContextChecker]},
    )
    selected = [issue for issue in issues if issue.rule.id == "TEST-1"]
    assert [issue.source_line for issue in selected] == ["src/demo/core.py"]


@pytest.mark.parametrize("quiet", ["", "1"])
def test_checker_crash_cannot_report_success(restore_environ, quiet):
    restore_environ["SCITEX_DEV_LINTER_QUIET"] = quiet
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="BrokenChecker.*coverage unavailable"
    ):
        lint_source(
            "x = 1\n",
            filepath="src/demo/core.py",
            plugins={"checkers": [BrokenChecker]},
        )


@pytest.mark.parametrize(
    "source",
    [
        'print("status")\n',
        "import json\nprint(json.dumps({}))\n",
        'def render(stream):\n    print("payload", file=stream)\n',
        "def render_content(content):\n    print(content)\n",
    ],
)
def test_injected_optional_payload_does_not_remove_mandatory_logging(source):
    issues = lint_source(
        source, filepath="src/demo/examples/core.py", plugins={"checkers": []}
    )
    assert len([issue for issue in issues if issue.rule.id == "PS-220"]) == 1


def test_disable_comments_and_severity_preferences_cannot_weaken_source_rule():
    config = LinterConfig(
        disable=["PS-220"],
        per_rule_severity={"PS-220": "info"},
        category_severity_override={"logging": "warning"},
    )
    issues = lint_source(
        'print("status") # stx-allow: PS-220\n',
        filepath="src/demo/core.py",
        config=config,
    )
    assert [issue.rule.severity for issue in issues if issue.rule.id == "PS-220"] == [
        "error"
    ]


def test_session_print_has_one_source_finding():
    issues = lint_source(
        'import scitex as stx\n@stx.session\ndef run():\n    print("status")\n',
        filepath="src/demo/core.py",
    )
    assert [
        issue.rule.id for issue in issues if issue.rule.id in {"PS-220", "STX-P005"}
    ] == ["PS-220"]


def test_real_io_and_figure_owners_both_run_once_with_existing_opt_in():
    source = 'fig.savefig("out.png", dpi=300)\n'
    ordinary = lint_source(source, filepath="src/demo/core.py", config=LinterConfig())
    opted = lint_source(
        source, filepath="src/demo/core.py", config=LinterConfig(enable=["FM"])
    )
    assert [issue.rule.id for issue in ordinary].count("STX-IO007") == 1
    assert "STX-FM006" not in [issue.rule.id for issue in ordinary]
    codes = [issue.rule.id for issue in opted]
    assert codes.count("STX-IO007") == codes.count("STX-FM006") == 1
