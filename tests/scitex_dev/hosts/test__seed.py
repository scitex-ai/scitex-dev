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

#: scitex-compute-04's single runner, measured 2026-08-12 from the GitHub
#: Actions API plus that machine's own `~/actions-runner-org/.runner`.
#: `sac-control-plane` is a CO-LOCATION label — see the seed's entry.
_CONTROL_PLANE_DESTINATION = (
    "scitex-compute-04",
    frozenset(
        {"self-hosted", "Linux", "X64", "scitex-org-cpu", "sac-control-plane"}
    ),
)

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

#: The whole floor, in `packaged_default_runner_destinations`' sort order
#: (by host name): scitex-compute-04 precedes spartan.
_SEED_DESTINATIONS = [_CONTROL_PLANE_DESTINATION, *_SPARTAN_DESTINATIONS]

_REGISTERED_HOSTS = [
    "mba",
    "scitex-compute-04",
    "scitex-nas-01",
    "scitex-nas-02",
    "scitex-nas-03",
    "spartan",
    "ywata-note-win",
]

#: The ssh aliases RETIRED on 2026-08-07. Each resolves to nothing on
#: purpose: the stub prints its successor and exits 255. Recorded in
#: ~/.ssh/retired-alias-hits.log, which is also where the successor names
#: below come from — they are read from the retirement mechanism, not
#: inferred from the naming pattern (`nas` -> `scitex-nas-03` is exactly
#: the pair a pattern would get wrong).
_RETIRED_SSH_ALIASES = {"nas", "nas1", "nas2", "nas3", "nas-01", "nas-02", "nas-03"}


def _seed_hosts() -> dict:
    """The seed's parsed `hosts:` mapping."""
    return (yaml.safe_load(_DEFAULT_HOSTS_YAML) or {})["hosts"]


def _seed_ssh_routes() -> set:
    """Every `ssh_alias` the seed hands out as a ROUTE (nulls dropped)."""
    return {
        (record or {}).get("ssh_alias")
        for record in _seed_hosts().values()
        if (record or {}).get("ssh_alias")
    }


def _seed_lookup_names() -> set:
    """Every name `resolve()` accepts — host keys PLUS their aliases."""
    names = set()
    for name, record in _seed_hosts().items():
        names.add(name)
        names.update((record or {}).get("aliases") or [])
    return names


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


def test_seed_hands_out_no_retired_ssh_route():
    # Arrange — reported by scitex-storage 2026-08-11: the seed served
    # `nas`/`nas1`/`nas2` for four days after they were retired, so this
    # registry was answering "how do I reach that host" with a name ssh
    # refuses. A discovery SSoT with a dead route is worse than no
    # registry, because consumers trust it.
    retired = _RETIRED_SSH_ALIASES
    # Act
    routes = _seed_ssh_routes()
    # Assert
    assert routes & retired == set()


def test_retired_route_would_be_caught_by_that_check():
    # Arrange — positive control. The assertion above passes both when the
    # seed is clean and when `_RETIRED_SSH_ALIASES` is empty or the route
    # extraction silently returns nothing, so on its own it cannot
    # distinguish "clean" from "did not look".
    routes = _seed_ssh_routes() | {"nas"}
    # Act
    caught = routes & _RETIRED_SSH_ALIASES
    # Assert
    assert caught == {"nas"}


def test_retired_names_still_resolve_as_lookup_aliases():
    # Arrange — the fix corrects the ROUTE, it does not delete the NAME. A
    # caller passing `nas` is using the name the fleet used until four days
    # ago and must still land on the successor record; turning a stale-route
    # bug into a KeyError would just move the breakage.
    retired = _RETIRED_SSH_ALIASES
    # Act
    lookup_names = _seed_lookup_names()
    # Assert
    assert retired <= lookup_names


def test_each_retired_alias_points_at_its_recorded_successor():
    # Arrange — the successors as the retirement stub itself logged them.
    recorded = {
        "nas": "scitex-nas-03",
        "nas3": "scitex-nas-03",
        "nas-03": "scitex-nas-03",
        "nas1": "scitex-nas-01",
        "nas-01": "scitex-nas-01",
        "nas2": "scitex-nas-02",
        "nas-02": "scitex-nas-02",
    }
    # Act
    found = {
        alias: name
        for name, record in _seed_hosts().items()
        for alias in (record or {}).get("aliases") or []
    }
    # Assert
    assert found == recorded


def test_packaged_floor_is_exactly_the_three_measured_label_sets():
    # Arrange — this list IS PS-224's floor; if a comment edit emptied it,
    # every workflow in the fleet would go unvalidated.
    expected = _SEED_DESTINATIONS
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
    assert len(found) == 3


def test_control_plane_label_travels_with_the_rest_of_its_runners_set():
    # Arrange — the seed's own rule: record the EFFECTIVE set the Actions API
    # reports, not just the `--labels` half. Registering `sac-control-plane`
    # ALONE would make every job that also names `Linux`/`X64` — i.e. every
    # job written in the fleet idiom — look unserved on this machine.
    expected = _CONTROL_PLANE_DESTINATION
    # Act
    found = [
        pair
        for pair in packaged_default_runner_destinations()
        if "sac-control-plane" in pair[1]
    ]
    # Assert
    assert found == [expected]


# EOF
