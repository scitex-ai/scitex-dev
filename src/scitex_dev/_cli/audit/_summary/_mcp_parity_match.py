"""§6 — pure Python-API ↔ MCP-tool name comparison (extracted from `_mcp_parity`).

No imports of the audited package and no file I/O: given the Python-API
names and the normalized MCP tool names, decide which tool covers which
API and which §6 violations follow. Split out so `_mcp_parity` (config
readers + orchestration) stays under the per-file line budget.
"""

from __future__ import annotations

from ._audit import Violation
from ._mcp_parity_baseline import ParityBaseline, ratchet_violations
from ._mcp_tool_naming import _OBJECT_FROM_PARAM_VERBS, STANDARD_TOOL_NAMES

__all__ = ["_parity_violations", "_tool_matches_api", "missing_python_apis"]


def _tool_matches_api(tool: str, api: str) -> bool:
    """Return True if `tool` covers `api` for §6 parity.

    A bare-name match (``tool == api``) always counts. We ALSO accept any
    ``<verb>_<api>`` form — i.e. the tool ends with ``_<api>`` — so an
    MCP tool named ``submit_sbatch`` satisfies §6 for the Python API
    ``sbatch``. This resolves the §2 / §6 conflict surfaced by #82:
    single-token Python APIs (the SLURM verb family ``sbatch`` /
    ``srun`` / ``squeue`` / ``sacct`` / ``scancel`` / ``salloc``, plus
    ``sync``, ``rsync``, etc.) previously could not satisfy both rules
    at once — §2 forbids single-token tool names, §6 demanded an
    exactly-matching MCP tool. Letting §6 accept the verb-prefixed form
    lets the package keep §2-compliant tool names while still passing
    §6.

    The mirror case is accepted too: a single-token API that §2 would
    REJECT as a bare tool name (``describe``, ``verify`` — neither a
    standard name nor a verb that takes its object as a parameter) can
    only be exposed as ``<api>_<noun>`` (``describe_data``,
    ``verify_result``). Verbs §2 accepts bare (``save``) gain nothing
    from this: their tool can, and must, carry the bare name.

    Both forms are one-way and need the FULL api string bounded by an
    underscore, so a totally-unrelated tool that merely shares a short
    affix with an API does not count.
    """
    if tool == api:
        return True
    if tool.endswith(f"_{api}"):
        return True
    return (
        "_" not in api
        and api not in _OBJECT_FROM_PARAM_VERBS
        and api not in STANDARD_TOOL_NAMES
        and tool.startswith(f"{api}_")
    )


def missing_python_apis(py_apis: set[str], mcp_normalized: set[str]) -> set[str]:
    """The Python APIs no MCP tool covers (see :func:`_tool_matches_api`)."""
    return {
        api
        for api in py_apis
        if not any(_tool_matches_api(t, api) for t in mcp_normalized)
    }


def _parity_violations(
    package: str,
    py_apis: set[str],
    mcp_normalized: set[str],
    baseline: ParityBaseline | None = None,
) -> list[Violation]:
    """Pure §6 comparison: given Python-API names and normalized MCP tool
    names, return the §6 violations (missing-in-MCP and orphan-tool).

    Split out from `_check_api_parity` so the comparison logic is testable
    with real sets — no module-import or registry I/O required.

    Matching uses :func:`_tool_matches_api`, which accepts the bare
    ``tool == api`` form, the ``<verb>_<api>`` form and (for single-token
    APIs §2 rejects as tool names) the ``<api>_<noun>`` form, so
    single-token Python APIs can satisfy both §2 (verb_noun naming) and §6
    (Python-API coverage) at the same time. See :func:`_tool_matches_api`
    docstring and #82 for the motivating conflict.

    ``baseline`` (a committed :class:`ParityBaseline`) replaces the
    more-than-half threshold of the missing-tool half with an exact
    ratchet: every missing API must be recorded, and every recorded API
    must still be missing. The orphan half is unaffected.
    """
    out: list[Violation] = []

    missing_in_mcp = missing_python_apis(py_apis, mcp_normalized)
    if baseline is not None:
        out.extend(ratchet_violations(package, missing_in_mcp, baseline))
    elif missing_in_mcp and len(missing_in_mcp) > len(py_apis) * 0.5:
        out.append(
            Violation(
                package,
                "§6",
                f"{len(missing_in_mcp)}/{len(py_apis)} Python APIs have no "
                f"matching MCP tool (sample: {sorted(missing_in_mcp)[:3]})",
            )
        )

    # Orphan check (warn-tier; small set is normal for envelope tools).
    # A tool that covers any Python API via the verb_<api> form is not
    # an orphan — same matching rule as the missing-in-MCP direction so
    # the two halves stay symmetric.
    skill_tools = {"skills_list", "skills_get"}
    orphans = {
        t
        for t in mcp_normalized
        if t not in skill_tools
        and not any(_tool_matches_api(t, api) for api in py_apis)
    }
    if orphans and len(orphans) > 3:
        out.append(
            Violation(
                package,
                "§6",
                f"{len(orphans)} MCP tools have no matching Python API "
                f"(sample: {sorted(orphans)[:3]}). This count is NOT one "
                "uniform task: some tools already have a real sync "
                "implementation and need only an export, while others have "
                "no Python API behind them at all and need a public "
                "signature designed. Do NOT satisfy this by re-exporting "
                "async MCP wrappers that return JSON strings — that "
                "publishes a transport shape as a Python API and is worse "
                "than the gap. See 03_interface/03_mcp/07_python-api-parity.",
            )
        )
    return out
