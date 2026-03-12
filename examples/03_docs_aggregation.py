#!/usr/bin/env python3
"""Example: Documentation aggregation across SciTeX packages."""

import json
from pathlib import Path

from scitex_dev import get_docs, search_docs

# Get docs overview for all packages
docs = get_docs()

output_dir = Path(__file__).parent / "03_docs_aggregation_out"
output_dir.mkdir(exist_ok=True)

with open(output_dir / "docs_overview.json", "w") as f:
    json.dump(
        docs if isinstance(docs, (list, dict)) else str(docs), f, indent=2, default=str
    )

print(f"Documentation overview saved to {output_dir / 'docs_overview.json'}")

# Search documentation
search_results = search_docs("installation")
with open(output_dir / "docs_search.json", "w") as f:
    json.dump(search_results, f, indent=2, default=str)

print(f"Documentation search results saved to {output_dir / 'docs_search.json'}")
