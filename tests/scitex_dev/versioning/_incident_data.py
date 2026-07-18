#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A recorded-shape version-currency incident, for the regression test.

sac's ``_freshness`` shipped a test that replayed the EXACT state of its
systems at 2026-07-13 23:30 — the moment a release run failed, three tags
never reached PyPI, and the fleet spent a day believing a merged fix was
live. That regression test is the whole point of the feature: it asks the
one question that matters — *would this alarm have fired, then, on that
data?*

This module carries the same idea, transposed onto scitex-dev's own version
line so the primitive is exercised against a realistic ecosystem, not tidy
invented numbers. The shape is faithful to the real failure family:

* the host has an OLDER version installed than what PyPI published, AND
* the HEAD release tag was tagged but never shipped (its release run failed).

Both conditions were simultaneously true and invisible in the sac outage.
The values below are a reconstruction in scitex-dev's numbering (its real
tags run to v0.31.1); they are labelled as such rather than passed off as a
live capture. What is NOT reconstructed is the assertion: on data of this
shape the verdict MUST be STALE, and if it ever reads FRESH the alarm is
worthless.
"""

from __future__ import annotations

# The host had this installed as a plain WHEEL while newer versions shipped.
INCIDENT_INSTALLED = "0.29.0"

# PyPI had published up to 0.31.0 — but NOT 0.31.1, whose tag exists.
INCIDENT_PYPI_LATEST = "0.31.0"
INCIDENT_PYPI_RELEASES = {
    "0.27.0", "0.28.0", "0.29.0", "0.30.0", "0.30.1", "0.31.0",
    # 0.31.1 absent — its tag exists, its release run FAILED. The ghost.
}

# Every v* tag in the checkout. v0.31.1 is the HEAD tag and never shipped.
INCIDENT_GIT_TAGS = [
    "v0.27.0", "v0.28.0", "v0.29.0", "v0.30.0", "v0.30.1",
    "v0.31.0", "v0.31.1",
]

# The head tag's release run ended in failure — build/publish never ran.
INCIDENT_RELEASE_RUNS = [
    {
        "conclusion": "failure",
        "status": "completed",
        "headBranch": "v0.31.1",
        "createdAt": "2026-07-16T23:24:19Z",
        "url": "https://github.com/scitex/scitex-dev/actions/runs/1",
    },
    {
        "conclusion": "success",
        "status": "completed",
        "headBranch": "v0.31.0",
        "createdAt": "2026-07-15T15:18:40Z",
        "url": "https://github.com/scitex/scitex-dev/actions/runs/2",
    },
]

# EOF
