"""Engine rules hand over to their declared owner — and only to it."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from importlib.metadata import EntryPoint

import pytest

from scitex_dev.linter import _plugin_loader
from scitex_dev.linter._rules import ALL_RULES
from scitex_dev.linter._rules._handover import HANDOVER, handover_owner
from scitex_dev.linter.checker import SciTeXChecker
from scitex_dev.linter.config import LinterConfig

GROUP = "scitex_dev.linter.plugins"
LOGGING = EntryPoint(
    name="scitex-logging", value="scitex_logging._linter_plugin:get_plugin", group=GROUP
)


@pytest.fixture(autouse=True)
def reset_cache():
    _plugin_loader.reset()
    yield
    _plugin_loader.reset()


@dataclass(frozen=True)
class Dist:
    """The distribution record an installed entry point carries."""

    name: str

    @property
    def metadata(self):
        return {"Name": self.name}


@dataclass
class OwnedProvider:
    """An entry point whose distribution ownership is explicit."""

    name: str
    distribution: str
    payload: object

    @property
    def value(self):
        return f"test_{self.name}:get_plugin"

    @property
    def dist(self):
        return Dist(self.distribution)

    def load(self):
        return lambda: self.payload


def discover(*providers):
    return _plugin_loader.load_plugins(entry_points_iter=lambda: (*providers, LOGGING))


def leaf_payload(rule_id):
    return {"rules": [ALL_RULES[rule_id]], "checkers": []}


def test_every_handover_id_is_an_engine_rule():
    # Arrange
    engine_ids = set(ALL_RULES)
    # Act
    unknown = set(HANDOVER) - engine_ids
    # Assert
    assert unknown == set()


def test_handover_owner_of_session_rule_is_scitex_session():
    # Arrange
    rule_id = "STX-S001"
    # Act
    owner = handover_owner(rule_id)
    # Assert
    assert owner == "scitex-session"


def test_declared_owner_takes_over_without_collision():
    # Arrange
    leaf = OwnedProvider("session", "scitex_session", leaf_payload("STX-S004"))
    # Act
    merged = discover(leaf)
    # Assert
    assert "STX-S004" in merged["handed_over"]


def test_undeclared_provider_claiming_engine_rule_still_collides():
    # Arrange
    impostor = OwnedProvider("other", "scitex-other", leaf_payload("STX-S004"))
    # Act
    attempt = lambda: discover(impostor)  # noqa: E731
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="already registered"):
        attempt()


def test_wrong_owner_cannot_take_a_handed_over_rule():
    # Arrange
    wrong = OwnedProvider("io", "scitex-io", leaf_payload("STX-S004"))
    # Act
    attempt = lambda: discover(wrong)  # noqa: E731
    # Assert
    with pytest.raises(_plugin_loader.LinterPluginError, match="already registered"):
        attempt()


def test_no_handover_without_owner_installed():
    # Arrange
    unrelated = OwnedProvider("x", "scitex-x", {"rules": [], "checkers": []})
    # Act
    merged = discover(unrelated)
    # Assert
    assert merged["handed_over"] == {}


def _lint_with_handed_over(source, handed_over):
    config = LinterConfig()
    checker = SciTeXChecker(source.splitlines(), filepath="tool.py", config=config)
    checker._handed_over = frozenset(handed_over)
    checker.visit(ast.parse(source))
    return {issue.rule.id for issue in checker.issues}


# STX-NM001 (`import mock`) has no `requires` gate, so these two run the
# same in every environment; the skip is keyed on the rule id alone.
def test_engine_keeps_emitting_rule_when_owner_absent():
    # Arrange
    source = "import mock\n"
    # Act
    ids = _lint_with_handed_over(source, ())
    # Assert
    assert "STX-NM001" in ids


def test_engine_stops_emitting_rule_once_handed_over():
    # Arrange
    source = "import mock\n"
    # Act
    ids = _lint_with_handed_over(source, {"STX-NM001"})
    # Assert
    assert "STX-NM001" not in ids


# EOF
