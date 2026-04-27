#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev.ecosystem_graph."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scitex_dev import ecosystem_graph as eg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_graph():
    """Hand-built adjacency dict — no filesystem access."""
    return {
        "scitex-io": {"hard": set(), "extras": {}},
        "scitex-stats": {
            "hard": {"scitex-io"},
            "extras": {"plt": {"scitex-plt"}},
        },
        "scitex-plt": {
            "hard": {"scitex-io"},
            "extras": {},
        },
        "scitex-writer": {
            "hard": {"scitex-stats", "scitex-plt"},
            "extras": {"all": {"scitex-io"}},
        },
        # Non-ecosystem deps must already be filtered out by parse_deps.
    }


@pytest.fixture
def cyclic_graph():
    """Synthetic graph with a 3-node cycle: A -> B -> C -> A."""
    return {
        "scitex-a": {"hard": {"scitex-b"}, "extras": {}},
        "scitex-b": {"hard": {"scitex-c"}, "extras": {}},
        "scitex-c": {"hard": {"scitex-a"}, "extras": {}},
        "scitex-d": {"hard": {"scitex-a"}, "extras": {}},  # off-cycle
    }


def _write_pyproject(path: Path, name: str, hard: list, extras: dict) -> Path:
    """Helper: write a minimal pyproject.toml at <path>."""
    extras_block = ""
    if extras:
        extras_block = "[project.optional-dependencies]\n"
        for k, v in extras.items():
            items = ", ".join(f'"{x}"' for x in v)
            extras_block += f"{k} = [{items}]\n"

    deps = ", ".join(f'"{x}"' for x in hard)
    content = (
        textwrap.dedent(
            f"""
        [project]
        name = "{name}"
        version = "0.0.1"
        dependencies = [{deps}]
        {extras_block}
        """
        ).strip()
        + "\n"
    )
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# parse_deps
# ---------------------------------------------------------------------------


def test_parse_deps_strips_version_specifiers(tmp_path):
    pp = _write_pyproject(
        tmp_path / "pyproject.toml",
        name="scitex-foo",
        hard=["scitex-io>=0.1.0", "scitex-stats==1.2.3", "scitex-plt~=0.5"],
        extras={},
    )
    info = eg.parse_deps(pp)
    assert info["name"] == "scitex-foo"
    assert info["hard"] == ["scitex-io", "scitex-plt", "scitex-stats"]


def test_parse_deps_filters_non_ecosystem_deps(tmp_path):
    pp = _write_pyproject(
        tmp_path / "pyproject.toml",
        name="scitex-foo",
        hard=["numpy>=1.20", "pandas", "scitex-io>=0.1.0", "requests"],
        extras={},
    )
    info = eg.parse_deps(pp)
    # numpy/pandas/requests must be dropped, only scitex-io remains.
    assert info["hard"] == ["scitex-io"]


def test_parse_deps_handles_extras_with_brackets(tmp_path):
    pp = _write_pyproject(
        tmp_path / "pyproject.toml",
        name="scitex-foo",
        hard=["scitex-io[extra1]>=0.1.0"],
        extras={"chat": ["scitex-stats[plotting]>=0.2.0", "anthropic>=0.25"]},
    )
    info = eg.parse_deps(pp)
    assert info["hard"] == ["scitex-io"]
    assert info["extras"] == {"chat": ["scitex-stats"]}


def test_parse_deps_drops_self_reference(tmp_path):
    pp = _write_pyproject(
        tmp_path / "pyproject.toml",
        name="scitex-foo",
        hard=[],
        extras={"all": ["scitex-foo[chat]", "scitex-io"]},
    )
    info = eg.parse_deps(pp)
    # self-reference removed from extras
    assert info["extras"] == {"all": ["scitex-io"]}


# ---------------------------------------------------------------------------
# discover_packages
# ---------------------------------------------------------------------------


def test_discover_packages_filters_by_regex(tmp_path):
    # Two ecosystem-named packages, one off-ecosystem.
    (tmp_path / "scitex-foo").mkdir()
    _write_pyproject(
        tmp_path / "scitex-foo" / "pyproject.toml",
        name="scitex-foo",
        hard=[],
        extras={},
    )
    (tmp_path / "figrecipe").mkdir()
    _write_pyproject(
        tmp_path / "figrecipe" / "pyproject.toml",
        name="figrecipe",
        hard=[],
        extras={},
    )
    (tmp_path / "random-thing").mkdir()
    _write_pyproject(
        tmp_path / "random-thing" / "pyproject.toml",
        name="random-thing",
        hard=[],
        extras={},
    )
    found = eg.discover_packages(roots=[tmp_path])
    assert set(found) == {"scitex-foo", "figrecipe"}


# ---------------------------------------------------------------------------
# build_graph + analysis
# ---------------------------------------------------------------------------


def test_build_graph_assembles_edges(tmp_path):
    (tmp_path / "scitex-io").mkdir()
    _write_pyproject(
        tmp_path / "scitex-io" / "pyproject.toml",
        name="scitex-io",
        hard=[],
        extras={},
    )
    (tmp_path / "scitex-stats").mkdir()
    _write_pyproject(
        tmp_path / "scitex-stats" / "pyproject.toml",
        name="scitex-stats",
        hard=["scitex-io>=0.1"],
        extras={"plt": ["scitex-plt>=0.1"]},
    )
    (tmp_path / "scitex-plt").mkdir()
    _write_pyproject(
        tmp_path / "scitex-plt" / "pyproject.toml",
        name="scitex-plt",
        hard=["scitex-io"],
        extras={},
    )

    pkgs = eg.discover_packages(roots=[tmp_path])
    graph = eg.build_graph(pkgs)
    assert graph["scitex-stats"]["hard"] == {"scitex-io"}
    assert graph["scitex-stats"]["extras"]["plt"] == {"scitex-plt"}
    assert graph["scitex-io"]["hard"] == set()


def test_find_cycles_detects_synthetic_cycle(cyclic_graph):
    cycles = eg.find_cycles(cyclic_graph, include_extras=False)
    assert len(cycles) == 1
    assert set(cycles[0]) == {"scitex-a", "scitex-b", "scitex-c"}


def test_find_cycles_returns_empty_on_dag(synthetic_graph):
    assert eg.find_cycles(synthetic_graph, include_extras=False) == []


def test_fan_in_out(synthetic_graph):
    fi, fo = eg.fan_in_out(synthetic_graph, include_extras=True)
    # scitex-io receives edges from stats, plt, writer (via 'all' extra)
    assert fi["scitex-io"] == 3
    # scitex-writer has hard {stats, plt} + extras {io} = 3 outgoing
    assert fo["scitex-writer"] == 3
    assert fo["scitex-io"] == 0


# ---------------------------------------------------------------------------
# Renderers (smoke tests)
# ---------------------------------------------------------------------------


def test_to_mermaid_emits_valid_header(synthetic_graph):
    out = eg.to_mermaid(synthetic_graph)
    assert out.startswith("graph LR")
    # Solid edge
    assert "scitex_stats --> scitex_io" in out
    # Dotted (extras-only) edge for stats -> plt
    assert "-.->" in out


def test_to_mermaid_no_extras_excludes_dotted(synthetic_graph):
    out = eg.to_mermaid(synthetic_graph, include_extras=False)
    assert "-.->" not in out


def test_to_dot_emits_digraph(synthetic_graph):
    out = eg.to_dot(synthetic_graph)
    assert out.startswith("digraph scitex_ecosystem {")
    assert "scitex_stats -> scitex_io;" in out
    # Extras edges marked dashed
    assert "style=dashed" in out
