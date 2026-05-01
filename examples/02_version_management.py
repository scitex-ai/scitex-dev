#!/usr/bin/env python3
"""Example: Version management across the SciTeX ecosystem.

Run:
    python 02_version_management.py
    python 02_version_management.py --help

Output:
    02_version_management_out/FINISHED_SUCCESS/<session_id>/
    ├── versions.json
    └── mismatches.json
"""

import json
from pathlib import Path

import scitex as stx

from scitex_dev import get_mismatches, list_versions


@stx.session
def main(
    CONFIG=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    """List versions for every package and surface any mismatches."""
    OUT = Path(CONFIG.SDIR_RUN)

    logger.info("Listing ecosystem versions")
    versions = list_versions()
    (OUT / "versions.json").write_text(json.dumps(versions, indent=2, default=str))

    logger.info("Detecting mismatches")
    mismatches = get_mismatches()
    (OUT / "mismatches.json").write_text(json.dumps(mismatches, indent=2, default=str))
    logger.info(f"Found {len(mismatches)} mismatch(es)")
    return 0


if __name__ == "__main__":
    main()
