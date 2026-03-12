#!/usr/bin/env python3
"""Example: Unified search across SciTeX ecosystem."""

import json
from pathlib import Path

from scitex_dev import search

# Search for documentation about figures
results = search("save figure")

output_dir = Path(__file__).parent / "01_unified_search_out"
output_dir.mkdir(exist_ok=True)

with open(output_dir / "search_results.json", "w") as f:
    json.dump(
        results if isinstance(results, (list, dict)) else str(results),
        f,
        indent=2,
        default=str,
    )

print(f"Search results saved to {output_dir / 'search_results.json'}")

# Search with scope
api_results = search("version", scope="api")
print(f"API-scoped search returned: {type(api_results)}")
