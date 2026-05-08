"""Smoke tests for the ecosystem dashboard state layer."""

from __future__ import annotations


def test_module_imports():
    from scitex_dev._cli.ecosystem._dashboard import _state  # noqa: F401


def test_gather_returns_list():
    from scitex_dev._cli.ecosystem._dashboard import gather_ecosystem_state

    states = gather_ecosystem_state(verbosity=0)
    assert isinstance(states, list)
    if states:
        assert hasattr(states[0], "pkg")
