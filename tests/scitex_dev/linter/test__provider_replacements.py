"""Exact provider transitions never hide unrelated or incomplete coverage."""

from dataclasses import dataclass
from importlib.metadata import EntryPoint
from types import SimpleNamespace

import os

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
def isolated_cache():
    # Arrange the process cache and notice flags with real environment
    # save/restore (no mocks): each test owns a clean loader state.
    _plugin_loader.reset()
    saved = {
        key: os.environ.pop(key, None)
        for key in ("SCITEX_DEV_LINTER_QUIET", "SCITEX_DEV_NO_AUDIT_DISCLAIMER")
    }
    yield
    for key, value in saved.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
    _plugin_loader.reset()


def _ordered(old, new, reverse):
    # One intent (both discovery orders); the ordering detail lives here
    # so parametrized bodies hold no branches.
    providers = [old, new]
    if reverse:
        providers.reverse()
    return providers


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_transition_covers_successor_and_logging_rules(reverse):
    # Arrange
    old, new = predecessor(), successor()
    # Act
    result = discover(*_ordered(old, new, reverse))
    # Assert
    assert set(result["rules"]) == {*IDS, "PS-220"}


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_transition_selects_successor_rule_objects(reverse):
    # Arrange
    old, new = predecessor(), successor()
    # Act
    result = discover(*_ordered(old, new, reverse))
    # Assert
    assert all(
        result["rules"][code] is new.payload["rules"][n] for n, code in enumerate(IDS)
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_transition_records_one_replacement_receipt(reverse):
    # Arrange
    old, new = predecessor(), successor()
    # Act
    result = discover(*_ordered(old, new, reverse))
    # Assert
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


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_transition_exposes_all_payload_keys(reverse):
    # Arrange
    old, new = predecessor(), successor()
    # Act
    result = discover(*_ordered(old, new, reverse))
    # Assert
    assert {"rules", "call_rules", "axes_hints", "checkers"} <= result.keys()


def test_old_provider_keeps_its_coverage_without_successor():
    # Arrange
    old = predecessor()
    # Act
    result = discover(old)
    # Assert
    assert all(
        result["rules"][code] is old.payload["rules"][n] for n, code in enumerate(IDS)
    )


def test_old_provider_records_no_replacement_without_successor():
    # Arrange
    old = predecessor()
    # Act
    result = discover(old)
    # Assert
    assert result["provider_replacements"] == ()


def test_successor_declaration_is_dormant_when_predecessor_has_no_advertised_provider():
    # Arrange
    # Supplied discovery is authoritative: a missing distribution and an installed
    # distribution with no linter entry point are indistinguishable and both safe.
    # Act
    new = successor()
    result = discover(new)
    # Assert
    assert set(result["rules"]) == {*IDS, "PS-220"}


def test_dormant_successor_declaration_records_no_replacement():
    # Arrange — same setup; a dormant declaration must not produce a receipt.
    new = successor()
    # Act
    result = discover(new)
    # Assert
    assert result["provider_replacements"] == ()


@pytest.mark.parametrize(
    "field,value", [("name", "other"), ("value", "scitex_ui.other:get_plugin")]
)
def test_named_distribution_with_unfamiliar_advertised_provider_is_rejected(
    field, value
):
    # Arrange
    # Act
    old = predecessor()
    setattr(old, field, value)
    # Assert
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="exact replacement contract"
    ):
        discover(old, successor())


def test_foreign_distribution_cannot_match_an_exact_entry_point_by_value_alone():
    # Arrange
    # Act
    old = predecessor()
    old.distribution = "foreign-ui"
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="duplicate rule"):
        discover(old, successor())


def test_distribution_names_follow_standard_metadata_normalization():
    # Arrange
    # Act
    old = predecessor()
    old.distribution = "SciTeX_UI"
    # Assert
    assert (
        discover(old, successor())["provider_replacements"][0][
            "predecessor_distribution"
        ]
        == "scitex-ui"
    )


@pytest.mark.parametrize("actual", [IDS[:-1], IDS + ("STX-UI999",)])
def test_predecessor_complete_rule_corpus_must_match_declared_ids(actual):
    # Arrange
    # Act
    # Assert
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="complete advertised rule IDs"
    ):
        discover(predecessor(actual), successor())


def test_successor_must_itself_offer_every_replaced_rule_even_if_predecessor_absent():
    # Arrange
    # Act
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="does not offer all"):
        discover(successor(ids=IDS[:-1]))


def test_successor_may_offer_additional_independently_owned_rules():
    # Arrange
    # Act
    result = discover(predecessor(), successor(ids=IDS + ("SDK-OTHER",)))
    # Assert
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
def test_malformed_replacement_is_fatal_even_when_dormant(declarations):
    # Arrange — quiet the notice through the real environment so the
    # fatal path is proved without notice text (no mocks).
    previous = os.environ.get("SCITEX_DEV_LINTER_QUIET")
    os.environ["SCITEX_DEV_LINTER_QUIET"] = "1"
    try:
        # Act
        with pytest.raises(
            _plugin_loader.LinterPluginError,
            match="replaces must be|invalid ProviderReplacement",
        ):
            discover(successor(declarations))
        # Assert: the expected raise above is the assertion
    finally:
        if previous is None:
            os.environ.pop("SCITEX_DEV_LINTER_QUIET", None)
        else:
            os.environ["SCITEX_DEV_LINTER_QUIET"] = previous


def test_self_replacement_is_rejected():
    # Arrange
    # Act
    new = successor((replacement("scitex-sdk", "ui", NEW_VALUE),))
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="self-replacement"):
        discover(new)


def test_repeated_replacement_is_rejected():
    # Arrange
    # Act
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="multiple or repeated"):
        discover(predecessor(), successor((replacement(), replacement())))


def test_competing_successors_are_rejected():
    # Arrange
    # Act
    other = Provider(
        "other-sdk", "other_sdk:get_plugin", payload(replaces=(replacement(),))
    )
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="multiple or repeated"):
        discover(predecessor(), successor(), other)


def test_cyclic_replacement_is_rejected():
    # Arrange
    # Act
    old = predecessor()
    old.payload["replaces"] = (replacement("scitex-sdk", "ui", NEW_VALUE),)
    # Assert
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="cyclic provider replacements"
    ):
        discover(old, successor())


def test_mandatory_logging_rule_cannot_be_displaced():
    # Arrange
    # Act
    new = successor(
        (replacement("scitex-logging", "scitex-logging", LOGGING.value, ("PS-220",)),),
        ids=("PS-220",),
    )
    # Assert
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="logging ownership cannot be replaced"
    ):
        discover(new)


def test_ordinary_collisions_without_replacement_remain_errors():
    # Arrange
    # Act
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="duplicate rule"):
        discover(predecessor(), successor(()))


def test_duplicate_ids_inside_replaced_payload_are_not_hidden():
    # Arrange
    # Act
    old = predecessor(IDS + (IDS[0],))
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="duplicate rule"):
        discover(old, successor())


def test_replacement_does_not_hide_a_broken_predecessor():
    # Arrange
    # Act
    old = predecessor()
    old.payload["checkers"] = [object()]
    # Assert
    with pytest.raises(
        _plugin_loader.LinterPluginError, match="checker must be callable"
    ):
        discover(old, successor())


def test_malformed_rule_severity_reports_provider_context():
    # Arrange
    # Act
    old = predecessor()
    old.payload["rules"][0] = Rule(IDS[0], [], "ui", "Malformed", "Fix")
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="scitex_ui.*invalid Rule"):
        discover(old, successor())


def test_replacement_does_not_hide_contradictory_predecessor_mapping():
    # Arrange
    # Act
    old = predecessor()
    old.payload["call_rules"] = {
        (None, "old_ui"): Rule(IDS[0], "error", "ui", "Contradictory", "Fix")
    }
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="contradictory rule"):
        discover(old, successor())


def test_replacement_does_not_hide_duplicate_predecessor_checker():
    # Arrange
    # Act
    old = predecessor()
    checker = lambda lines, config: None
    old.payload["checkers"] = [checker, checker]
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="duplicate checker"):
        discover(old, successor())


def test_quiet_suppresses_only_notice_and_retains_receipt(caplog):
    # Arrange
    caplog.set_level(20)
    # Act
    result = discover(predecessor(), successor())
    notices = [
        record for record in caplog.records if " replaces " in record.getMessage()
    ]
    # Assert
    assert len(notices) == 1


def test_quiet_discovery_keeps_the_same_replacement_receipt(caplog):
    # Arrange
    caplog.set_level(20)
    result = discover(predecessor(), successor())
    caplog.clear()
    previous = os.environ.get("SCITEX_DEV_LINTER_QUIET")
    os.environ["SCITEX_DEV_LINTER_QUIET"] = "1"
    try:
        # Act
        quiet = discover(predecessor(), successor())
        # Assert — one statement: receipts equal and non-empty.
        assert quiet["provider_replacements"] == result["provider_replacements"] != ()
    finally:
        if previous is None:
            os.environ.pop("SCITEX_DEV_LINTER_QUIET", None)
        else:
            os.environ["SCITEX_DEV_LINTER_QUIET"] = previous


def test_quiet_discovery_emits_no_replacement_notice(caplog):
    # Arrange
    caplog.set_level(20)
    discover(predecessor(), successor())
    caplog.clear()
    previous = os.environ.get("SCITEX_DEV_LINTER_QUIET")
    os.environ["SCITEX_DEV_LINTER_QUIET"] = "1"
    try:
        # Act
        discover(predecessor(), successor())
        # Assert
        assert not any(" replaces " in record.getMessage() for record in caplog.records)
    finally:
        if previous is None:
            os.environ.pop("SCITEX_DEV_LINTER_QUIET", None)
        else:
            os.environ["SCITEX_DEV_LINTER_QUIET"] = previous


def test_cached_discovery_reports_active_transition_once(caplog):
    # Arrange — controlled discovery source through direct save/restore
    # (no mock framework); the injected providers are real constructed
    # objects, and the loader's real validation + cache run unmodified.
    caplog.set_level(20)
    previous = _plugin_loader._iter_entry_points
    _plugin_loader._iter_entry_points = (
        lambda group: (predecessor(), successor(), LOGGING)
    )
    try:
        # Act
        first = _plugin_loader.load_plugins()
        # Assert
        assert _plugin_loader.load_plugins() is first
    finally:
        _plugin_loader._iter_entry_points = previous


def test_cached_discovery_emits_exactly_one_transition_notice(caplog):
    # Arrange — same controlled source; the notice count is the assertion.
    caplog.set_level(20)
    previous = _plugin_loader._iter_entry_points
    _plugin_loader._iter_entry_points = (
        lambda group: (predecessor(), successor(), LOGGING)
    )
    try:
        # Act
        _plugin_loader.load_plugins()
        # Assert
        assert (
            len(
                [record for record in caplog.records if " replaces " in record.getMessage()]
            )
            == 1
        )
    finally:
        _plugin_loader._iter_entry_points = previous


def test_owned_entry_point_retains_distribution_ownership():
    # Arrange — plain data objects, no mocks and no interpreter patching.
    point = SimpleNamespace(name="ui", value="x:y", load=lambda: lambda: {})
    dist = SimpleNamespace(metadata={"Name": "scitex-ui"})
    # Act
    owned = _plugin_loader._OwnedEntryPoint(point, dist)
    # Assert
    assert owned.dist is dist


def test_legacy_discovery_wraps_points_with_their_distributions():
    # Arrange — the legacy branch is pinned by data: an explicit version,
    # real installed distributions, no interpreter patching.
    # Act
    points = list(_plugin_loader._iter_entry_points(GROUP, _version_info=(3, 9)))
    # Assert
    assert all(isinstance(point, _plugin_loader._OwnedEntryPoint) for point in points)
