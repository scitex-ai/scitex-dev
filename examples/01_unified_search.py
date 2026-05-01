#!/usr/bin/env python3
"""Example: Unified search across SciTeX ecosystem.

Run:
    python 01_unified_search.py
    python 01_unified_search.py --query "save figure"
    python 01_unified_search.py --help

Output:
    01_unified_search_out/FINISHED_SUCCESS/<session_id>/
    ├── search_results.json
    └── api_search_results.json
"""

import json
from pathlib import Path

import scitex as stx

from scitex_dev import search


@stx.session
def main(
    query: str = "save figure",  # python 01_unified_search.py --query "..."
    CONFIG=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    """Demonstrate scitex-dev's unified search across docs/APIs/CLI/MCP."""
    OUT = Path(CONFIG.SDIR_RUN)

    logger.info(f"Searching for: {query!r}")
    results = search(query)
    out_path = OUT / "search_results.json"
    with open(out_path, "w") as f:
        json.dump(
            results if isinstance(results, (list, dict)) else str(results),
            f,
            indent=2,
            default=str,
        )
    logger.info(f"Wrote {out_path}")

    logger.info("Searching with scope=api")
    api_results = search("version", scope="api")
    api_path = OUT / "api_search_results.json"
    with open(api_path, "w") as f:
        json.dump(
            api_results if isinstance(api_results, (list, dict)) else str(api_results),
            f,
            indent=2,
            default=str,
        )
    logger.info(f"Wrote {api_path}")
    return 0


if __name__ == "__main__":
    main()
