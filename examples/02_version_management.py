#!/usr/bin/env python3
"""Example: Version management across the SciTeX ecosystem."""

import json
from pathlib import Path

from scitex_dev import list_versions, get_mismatches

# List all ecosystem versions
versions = list_versions()

output_dir = Path(__file__).parent / "02_version_management_out"
output_dir.mkdir(exist_ok=True)

with open(output_dir / "versions.json", "w") as f:
    json.dump(versions, f, indent=2, default=str)

print(f"Ecosystem versions saved to {output_dir / 'versions.json'}")

# Check for mismatches
mismatches = get_mismatches()
with open(output_dir / "mismatches.json", "w") as f:
    json.dump(mismatches, f, indent=2, default=str)

print(f"Mismatches saved to {output_dir / 'mismatches.json'}")
