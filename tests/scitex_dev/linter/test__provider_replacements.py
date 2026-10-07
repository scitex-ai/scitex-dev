"""Exact provider transitions never hide unrelated or incomplete coverage."""

from dataclasses import dataclass
from importlib.metadata import EntryPoint
from types import SimpleNamespace

import pytest

from scitex_dev.linter import _plugin_loader
from scitex_dev.linter.spi import ProviderReplacement, Rule

GROUP = "scitex_dev.linter.plugins"
LOGGING = EntryPoint(
    name="scitex-logging", value="scitex_logging._linter_plugin:get_plugin", group=GROUP
)
IDS = tuple(f"STX-UI{number}" for number in range(101, 108))
OLD_VALUE = "scitex_ui._linter_plugin:get_plugin"
NEW_VALUE = "scitex_sdk.ui._linter_plugin:get_plugin"


@dataclass
class Provider:
    distribution: str
    value: str
    payload: dict
    name: str = "ui"

    @property
    def dist(self):
        return SimpleNamespace(metadata={"Name": self.distribution})

    def load(self):
        return lambda: self.payload


def payload(ids=IDS, **extras):
    return {
        "rules": [
            Rule(code, "warning", "ui", "Use shared UI", "Use SDK") for code in ids
        ],
        "call_rules": {},
        "axes_hints": {},
        "checkers": [],
        **extras,
    }


def replacement(
    distribution="scitex-ui", entry_point="ui", value=OLD_VALUE, rule_ids=IDS
):
    return ProviderReplacement(distribution, entry_point, value, rule_ids)


def predecessor(ids=IDS, **fields):
    return Provider("scitex-ui", OLD_VALUE, payload(ids), **fields)


def successor(declarations=None, ids=IDS):
    if declarations is None:
        declarations = (replacement(),)
    return Provider("scitex-sdk", NEW_VALUE, payload(ids, replaces=declarations))


def discover(*providers):
    return _plugin_loader.load_plugins(entry_points_iter=lambda: (*providers, LOGGING))


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    _plugin_loader.reset()
    monkeypatch.delenv("SCITEX_DEV_LINTER_QUIET", raising=False)
    monkeypatch.delenv("SCITEX_DEV_NO_AUDIT_DISCLAIMER", raising=False)
    yield
    _plugin_loader.reset()


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_transition_selects_successor_in_both_discovery_orders(reverse):
    old, new = predecessor(), successor()
    providers = [old, new]
    if reverse:
        providers.reverse()
    result = discover(*providers)
    assert set(result["rules"]) == {*IDS, "PS-220"}
    assert all(
        result["rules"][code] is new.payload["rules"][n] for n, code in enumerate(IDS)
    )
    assert result["provider_replacements"] == (
        {
            "successor_distribution": "scitex-sdk",
            "successor_entry_point": "ui",
            "successor_value": NEW_VALUE,
            "predecessor_distribution": "scitex-ui",
            "predecessor_entry_point": "ui",
            "predecessor_value": OLD_VALUE,
            "rule_ids": IDS,
        },
    )
    assert {"rules", "call_rules", "axes_hints", "checkers"} <= result.keys()


def test_old_provider_keeps_its_coverage_without_successor():
    old = predecessor()
    result = discover(old)
    assert all(
        result["rules"][code] is old.payload["rules"][n] for n, code in enumerate(IDS)
    )
    assert result["provider_replacements"] == ()


def test_successor_declaration_is_dormant_when_predecessor_has_no_advertised_provider():
    # Supplied discovery is authoritative: a missing distribution and an installed
    # distribution with no linter entry point are indistinguishable and both safe.
    new = successor()
    result = discover(new)
    assert set(result["rules"]) == {*IDS, "PS-220"}
    assert result["provider_replacements"] == ()


@pytest.mark.parametrize(
    "field,value", [("name", "other"), ("value", "scitex_ui.other:get_plugin")]
)
def test_named_distribution_with_unfamiliar_advertised_provider_is_rejected(
    field, value
):
    old = predecessor()
    setattr(old, field, value)
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="exact replacement contract"
    ):
        discover(old, successor())


def test_foreign_distribution_cannot_match_an_exact_entry_point_by_value_alone():
    old = predecessor()
    old.distribution = "foreign-ui"
    with pytest.raises(_plugin_loader.LinterPluginError, match="duplicate rule"):
        discover(old, successor())


def test_distribution_names_follow_standard_metadata_normalization():
    old = predecessor()
    old.distribution = "SciTeX_UI"
    assert (
        discover(old, successor())["provider_replacements"][0][
            "predecessor_distribution"
        ]
        == "scitex-ui"
    )


@pytest.mark.parametrize("actual", [IDS[:-1], IDS + ("STX-UI999",)])
def test_predecessor_complete_rule_corpus_must_match_declared_ids(actual):
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="complete advertised rule IDs"
    ):
        discover(predecessor(actual), successor())


def test_successor_must_itself_offer_every_replaced_rule_even_if_predecessor_absent():
    with pytest.raises(_plugin_loader.LinterPluginError, match="does not offer all"):
        discover(successor(ids=IDS[:-1]))


def test_successor_may_offer_additional_independently_owned_rules():
    result = discover(predecessor(), successor(ids=IDS + ("SDK-OTHER",)))
    assert "SDK-OTHER" in result["rules"]


@pytest.mark.parametrize(
    "declarations",
    [
        [],
        ("ignored declaration",),
        (replacement(distribution=""),),
        (replacement(entry_point=""),),
        (replacement(value=""),),
        (replacement(rule_ids=()),),
        (replacement(rule_ids=list(IDS)),),
        (replacement(rule_ids=IDS + (IDS[0],)),),
        (replacement(rule_ids=("",)),),
    ],
)
def test_malformed_replacement_is_fatal_even_when_dormant(declarations, monkeypatch):
    monkeypatch.setenv("SCITEX_DEV_LINTER_QUIET", "1")
    with pytest.raises(
        _plugin_loader.LinterPluginError,
        match="replaces must be|invalid ProviderReplacement",
    ):
        discover(successor(declarations))


def test_self_replacement_is_rejected():
    new = successor((replacement("scitex-sdk", "ui", NEW_VALUE),))
    with pytest.raises(_plugin_loader.LinterPluginError, match="self-replacement"):
        discover(new)


def test_repeated_replacement_is_rejected():
    with pytest.raises(_plugin_loader.LinterPluginError, match="multiple or repeated"):
        discover(predecessor(), successor((replacement(), replacement())))


def test_competing_successors_are_rejected():
    other = Provider(
        "other-sdk", "other_sdk:get_plugin", payload(replaces=(replacement(),))
    )
    with pytest.raises(_plugin_loader.LinterPluginError, match="multiple or repeated"):
        discover(predecessor(), successor(), other)


def test_cyclic_replacement_is_rejected():
    old = predecessor()
    old.payload["replaces"] = (replacement("scitex-sdk", "ui", NEW_VALUE),)
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="cyclic provider replacements"
    ):
        discover(old, successor())


def test_mandatory_logging_rule_cannot_be_displaced():
    new = successor(
        (replacement("scitex-logging", "scitex-logging", LOGGING.value, ("PS-220",)),),
        ids=("PS-220",),
    )
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="logging ownership cannot be replaced"
    ):
        discover(new)


def test_ordinary_collisions_without_replacement_remain_errors():
    with pytest.raises(_plugin_loader.LinterPluginError, match="duplicate rule"):
        discover(predecessor(), successor(()))


def test_duplicate_ids_inside_replaced_payload_are_not_hidden():
    old = predecessor(IDS + (IDS[0],))
    with pytest.raises(_plugin_loader.LinterPluginError, match="duplicate rule"):
        discover(old, successor())


def test_replacement_does_not_hide_a_broken_predecessor():
    old = predecessor()
    old.payload["checkers"] = [object()]
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="checker must be callable"
    ):
        discover(old, successor())


def test_malformed_rule_severity_reports_provider_context():
    old = predecessor()
    old.payload["rules"][0] = Rule(IDS[0], [], "ui", "Malformed", "Fix")
    with pytest.raises(_plugin_loader.LinterPluginError, match="scitex_ui.*invalid Rule"):
        discover(old, successor())


def test_replacement_does_not_hide_contradictory_predecessor_mapping():
    old = predecessor()
    old.payload["call_rules"] = {
        (None, "old_ui"): Rule(IDS[0], "error", "ui", "Contradictory", "Fix")
    }
    with pytest.raises(_plugin_loader.LinterPluginError, match="contradictory rule"):
        discover(old, successor())


def test_replacement_does_not_hide_duplicate_predecessor_checker():
    old = predecessor()
    checker = lambda lines, config: None
    old.payload["checkers"] = [checker, checker]
    with pytest.raises(_plugin_loader.LinterPluginError, match="duplicate checker"):
        discover(old, successor())


def test_quiet_suppresses_only_notice_and_retains_receipt(monkeypatch, caplog):
    caplog.set_level(20)
    result = discover(predecessor(), successor())
    notices = [
        record for record in caplog.records if " replaces " in record.getMessage()
    ]
    assert len(notices) == 1
    assert result["provider_replacements"]
    caplog.clear()
    monkeypatch.setenv("SCITEX_DEV_LINTER_QUIET", "1")
    quiet = discover(predecessor(), successor())
    assert quiet["provider_replacements"] == result["provider_replacements"]
    assert not any(" replaces " in record.getMessage() for record in caplog.records)


def test_cached_discovery_reports_active_transition_once(monkeypatch, caplog):
    caplog.set_level(20)
    monkeypatch.setattr(
        _plugin_loader,
        "_iter_entry_points",
        lambda group: (predecessor(), successor(), LOGGING),
    )
    first = _plugin_loader.load_plugins()
    assert _plugin_loader.load_plugins() is first
    assert (
        len(
            [record for record in caplog.records if " replaces " in record.getMessage()]
        )
        == 1
    )


def test_python39_discovery_retains_actual_distribution_ownership(monkeypatch):
    from importlib import metadata

    old, new = predecessor(), successor()

    class OwnerlessPoint:
        group = GROUP

        def __init__(self, provider):
            self.name = provider.name
            self.value = provider.value
            self.load = provider.load

    old_point, new_point = OwnerlessPoint(old), OwnerlessPoint(new)
    logger_dist = SimpleNamespace(
        metadata={"Name": "scitex-logging"}, entry_points=[LOGGING]
    )
    old_dist = SimpleNamespace(
        metadata={"Name": old.distribution}, entry_points=[old_point]
    )
    new_dist = SimpleNamespace(
        metadata={"Name": new.distribution}, entry_points=[new_point]
    )
    monkeypatch.setattr(_plugin_loader.sys, "version_info", (3, 9))
    monkeypatch.setattr(
        metadata, "distributions", lambda: (old_dist, new_dist, logger_dist)
    )

    def forbidden_flattened_metadata(*args, **kwargs):
        pytest.fail("flattened Python 3.9 entry points lack owner identity")

    monkeypatch.setattr(metadata, "entry_points", forbidden_flattened_metadata)
    result = _plugin_loader.load_plugins()
    assert result["provider_replacements"][0]["predecessor_distribution"] == "scitex-ui"
    assert result["provider_replacements"][0]["successor_distribution"] == "scitex-sdk"
