"""Owned source witnesses for conservative MCP suffix contradiction checks."""

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

from scitex_dev._cli.audit._summary._mcp_binding import suffix_contradictions
from scitex_dev._cli.audit._summary._mcp_parity import _parity_violations


def _fixture(tmp_path, body, *, extra=""):
    source = tmp_path / "src" / "fixture_ops"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text(
        "from .operations import search, search_docs, sbatch\n"
        "__all__ = ['search', 'search_docs', 'sbatch']\n"
    )
    (source / "operations.py").write_text(
        "def search(query):\n    raise AssertionError('domain call forbidden')\n"
        "def search_docs(query):\n    raise AssertionError('domain call forbidden')\n"
        "def sbatch(query):\n    raise AssertionError('domain call forbidden')\n"
    )
    path = source / "tools.py"
    path.write_text(extra + "\ndef mcp_docs_search(query):\n" + body)
    # Own fixture definitions only. Imports remain inside the uncalled wrapper.
    spec = spec_from_file_location("fixture_ops.tools", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return SimpleNamespace(name="mcp_docs_search", fn=module.mcp_docs_search)


def _check(repo, tool):
    return suffix_contradictions(
        "fixture-ops", {"search", "search_docs", "sbatch"}, [tool], repo
    )


def test_owned_wrapper_to_different_public_boundary_vetoes_suffix(tmp_path):
    """A genuine source contradiction cannot count as search coverage."""
    # Arrange
    tool = _fixture(
        tmp_path,
        "    from .operations import search_docs\n    return search_docs(query)\n",
    )
    # Act
    vetoes, notes = _check(tmp_path, tool)
    violations = _parity_violations(
        "fixture-ops", {"search"}, {"mcp_docs_search"}, contradicted_pairs=vetoes
    )
    # Assert
    observed = {
        "vetoes": vetoes,
        "first_public_apis": notes["contradictions"][0]["first_public_apis"],
        "violation_count": len(violations),
        "missing_reported": "1/1 Python APIs" in violations[0].message,
    }
    assert observed == {
        "vetoes": {("mcp_docs_search", "search")},
        "first_public_apis": ["search_docs"],
        "violation_count": 1,
        "missing_reported": True,
    }


def test_genuine_prefix_wrapper_preserves_suffix_coverage(tmp_path):
    """The existing submit_sbatch convention is still accepted."""
    # Arrange
    tool = _fixture(
        tmp_path, "    from .operations import sbatch\n    return sbatch(query)\n"
    )
    tool.name = "submit_sbatch"
    # Act
    vetoes, notes = _check(tmp_path, tool)
    # Assert
    assert (vetoes, notes["verified_suffix_boundaries"]) == (
        set(),
        [{"tool": "submit_sbatch", "api": "sbatch"}],
    )


@pytest.mark.parametrize(
    "body,extra",
    [
        (
            "    from .operations import search_docs\n    if query:\n        return search_docs(query)\n",
            "",
        ),
        (
            "    from .operations import search_docs\n    if False:\n        return search_docs(query)\n    return query\n",
            "",
        ),
        (
            "    return query\n    from .operations import search_docs\n    search_docs(query)\n",
            "",
        ),
        (
            "    if True:\n        return query\n    from .operations import search_docs\n    search_docs(query)\n",
            "",
        ),
        (
            "    return helper(query)\n",
            "def helper(query):\n    return mcp_docs_search(query)\n",
        ),
        (
            "    import foreign\n    return foreign.search_docs(query)\n",
            "",
        ),
        (
            "    from . import operations\n    return getattr(operations, query)(query)\n",
            "",
        ),
    ],
)
def test_ambiguous_dead_dynamic_foreign_or_cyclic_calls_are_unproven(
    tmp_path, body, extra
):
    """No speculative path may establish a contradiction or verified coverage."""
    # Arrange
    tool = _fixture(tmp_path, body, extra=extra)
    # Act
    vetoes, notes = _check(tmp_path, tool)
    # Assert
    assert (
        vetoes,
        notes["verified_suffix_boundaries"],
        bool(notes["unproven_suffix_matches"]),
    ) == (set(), [], True)


def test_same_name_owned_private_function_is_not_a_public_api(tmp_path):
    """Matching spelling in another owner does not prove a public binding."""
    # Arrange
    tool = _fixture(
        tmp_path,
        "    return search_docs(query)\n",
        extra="def search_docs(query):\n    return query\n",
    )
    # Act
    vetoes, notes = _check(tmp_path, tool)
    # Assert
    assert not vetoes and notes["unproven_suffix_matches"]


def test_captured_callback_is_unproven_without_inspecting_or_invoking_it(tmp_path):
    """A runtime closure cannot be replaced by a same-spelled global source."""
    # Arrange
    tool = _fixture(
        tmp_path,
        "    return query\n",
        extra=(
            "def factory(search_docs):\n"
            "    def mcp_docs_search(query):\n"
            "        return search_docs(query)\n"
            "    return mcp_docs_search\n"
        ),
    )
    tool.fn = tool.fn.__globals__["factory"](object())
    # Act
    vetoes, notes = _check(tmp_path, tool)
    # Assert
    assert (vetoes, notes["unproven_suffix_matches"][0]["reasons"]) == (
        set(),
        ["closure-binding"],
    )


def test_first_public_boundary_is_not_followed_into_its_implementation(tmp_path):
    """An implementation's own dependencies never redefine its public owner."""
    # Arrange
    tool = _fixture(
        tmp_path, "    from .operations import search\n    return search(query)\n"
    )
    (tmp_path / "src/fixture_ops/operations.py").write_text(
        "def search(query):\n    return search_docs(query)\n"
        "def search_docs(query):\n    raise AssertionError('never invoke')\n"
        "def sbatch(query):\n    return query\n"
    )
    # Act
    vetoes, notes = _check(tmp_path, tool)
    # Assert
    assert (vetoes, notes["verified_suffix_boundaries"]) == (
        set(),
        [{"tool": "mcp_docs_search", "api": "search"}],
    )


@pytest.mark.parametrize(
    "body",
    [
        "    from .operations import search_docs as operation\n    return operation(query)\n",
        "    from . import operations as operations\n    return operations.search_docs(query)\n",
        "    from .operations import search_docs\n    alias = search_docs\n    return alias(query)\n",
    ],
)
def test_owned_source_aliases_keep_actual_public_identity(tmp_path, body):
    """Simple source imports and aliases are evidence, not name coincidences."""
    # Arrange
    tool = _fixture(tmp_path, body)
    # Act
    vetoes, notes = _check(tmp_path, tool)
    # Assert
    assert (vetoes, notes["contradictions"][0]["first_public_apis"]) == (
        {("mcp_docs_search", "search")},
        ["search_docs"],
    )


def test_actual_dev_docs_wrapper_calls_search_docs_not_search():
    """Registration metadata is inspected; no actual documentation tool runs."""
    # Arrange
    from fastmcp import FastMCP

    from scitex_dev._ecosystem._mcp import get_tools_sync
    from scitex_dev._ecosystem._mcp._core import register_docs_tools

    mcp = FastMCP("owned-source-witness")
    register_docs_tools(mcp)
    tools = list(get_tools_sync(mcp).values())
    repo = Path(__file__).resolve().parents[5]
    # Act
    vetoes, notes = suffix_contradictions(
        "scitex-dev", {"search", "search_docs"}, tools, repo
    )
    # Assert
    observed = {
        "vetoed": ("mcp_docs_search", "search") in vetoes,
        "contradictions": notes["contradictions"],
    }
    assert observed == {
        "vetoed": True,
        "contradictions": [
            {
                "tool": "mcp_docs_search",
                "api": "search",
                "first_public_apis": ["search_docs"],
            }
        ],
    }


def test_actual_auditor_json_retains_debt_and_explains_source_basis(capfd):
    """The public audit reports its real findings and the bounded veto basis."""
    # Arrange
    from scitex_dev._cli.audit._summary._mcp_audit import run_audit_mcp

    repo = Path(__file__).resolve().parents[5]
    # Act
    code = run_audit_mcp("scitex-dev", output_json=True, repo=repo)
    payload = json.loads(capfd.readouterr().out)
    result = payload["results"][0]
    # Assert
    observed = {
        "exit": code,
        "rules": sorted({item["rule"] for item in result["violations"]}),
        "contradictions": result["parity_basis"]["contradictions"],
    }
    assert observed == {
        "exit": 1,
        "rules": ["§6"],
        "contradictions": [
            {
                "tool": "mcp_docs_search",
                "api": "search",
                "first_public_apis": ["search_docs"],
            }
        ],
    }
