#!/usr/bin/env python3
"""Example: Documentation aggregation across SciTeX packages.

Run:
    python 03_docs_aggregation.py
    python 03_docs_aggregation.py --query "save figure"
    python 03_docs_aggregation.py --help

Output:
    03_docs_aggregation_out/FINISHED_SUCCESS/<session_id>/
    ├── docs_overview.json
    └── search_hits.json
"""

import json
from pathlib import Path

import scitex as stx

from scitex_dev import get_docs, search_docs


@stx.session
def main(
    query: str = "save figure",
    CONFIG=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    """Show every package's docs surface and search across all docs."""
    OUT = Path(CONFIG.SDIR_RUN)

    logger.info("Aggregating package docs overviews")
    docs = get_docs()
    (OUT / "docs_overview.json").write_text(json.dumps(docs, indent=2, default=str))

    logger.info(f"Searching docs for: {query!r}")
    hits = search_docs(query)
    (OUT / "search_hits.json").write_text(json.dumps(hits, indent=2, default=str))
    logger.info(f"Got {len(hits) if hasattr(hits, '__len__') else '?'} hits")
    return 0


if __name__ == "__main__":
    main()
