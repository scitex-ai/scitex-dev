"""The SHIPPED registry seed must keep parsing — it is PS-224's whole floor.

`_DEFAULT_HOSTS_YAML` is a YAML string carrying a large, growing block of
operational guidance in COMMENTS (how to record `runner_labels`, and which
label breadth to ask for in a workflow). Comments are where that guidance
belongs — the seed is the only copy of the registry that reaches every host
— but they sit INSIDE the parsed constant, so a mis-indented or
accidentally-uncommented line changes what `yaml.safe_load` sees.

The failure that would cause is silent and total: an empty
`packaged_default_runner_destinations()` takes down PS-224's floor, and the
rule degrades to "the registry records NO destinations, could not check" —
exactly the unverifiable state the rule exists to prevent. So the seed's
PARSED content is pinned here, independently of its prose.

No mocks (NM001-003): the packaged constant is read as shipped.
One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

import yaml

from scitex_dev.hosts import packaged_default_runner_destinations
from scitex_dev.hosts._seed import _DEFAULT_HOSTS_YAML

#: spartan's two live runner label sets, measured 2026-07-24 from the
#: GitHub Actions API. `spartan-cpu` is on every runner; `scitex-ci` only on
#: the pooled subset — see the seed's own CHOOSING LABELS comment.
_SPARTAN_DESTINATIONS = [
    ("spartan", frozenset({"self-hosted", "Linux", "X64", "spartan-cpu"})),
    (
        "spartan",
        frozenset({"self-hosted", "Linux", "X64", "spartan-cpu", "scitex-ci"}),
    ),
]

_REGISTERED_HOSTS = ["mba", "nas", "nas1", "nas2", "spartan", "ywata-note-win"]


def test_seed_yaml_still_parses_as_a_mapping():
    # Arrange — a comment-block edit must not break the parse.
    seed = _DEFAULT_HOSTS_YAML
    # Act
    parsed = yaml.safe_load(seed)
    # Assert
    assert isinstance(parsed, dict)


def test_seed_yaml_still_declares_every_registered_host():
    # Arrange
    seed = _DEFAULT_HOSTS_YAML
    # Act
    parsed = yaml.safe_load(seed)
    # Assert
    assert sorted(parsed["hosts"]) == _REGISTERED_HOSTS


def test_packaged_floor_is_exactly_spartans_two_label_sets():
    # Arrange — this list IS PS-224's floor; if a comment edit emptied it,
    # every workflow in the fleet would go unvalidated.
    expected = _SPARTAN_DESTINATIONS
    # Act
    found = packaged_default_runner_destinations()
    # Assert
    assert found == expected


def test_packaged_floor_is_never_empty():
    # Arrange — the explicit anti-silent-degradation guard: an empty floor
    # is indistinguishable from "checked and clean" at a glance.
    pass
    # Act
    found = packaged_default_runner_destinations()
    # Assert
    assert found


def test_seed_label_sets_are_per_runner_not_a_flattened_union():
    # Arrange — a flattened union would green-light a combination no single
    # runner offers, and such a job queues forever.
    pass
    # Act
    found = packaged_default_runner_destinations()
    # Assert
    assert len(found) == 2


# EOF
