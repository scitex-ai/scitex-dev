"""Reviewed reusable workflow bytes, independent of a normal merge commit SHA.

The group must select all seven native job definitions at one full revision.
The hosted admission workflow at that same revision is checked too. Public
source qualification never mutates the group's selected revisions.
"""
from __future__ import annotations

import base64
import hashlib
import re

NATIVE_WORKFLOWS = (
    "auto-merge-to-develop.yml", "cla.yml", "import-smoke.yml",
    "promote-develop-to-main-on-tag.yml", "pytest-matrix.yml",
    "quality-audit.yml", "rtd-sphinx-build.yml",
)
# Exact hashes are generated from the reviewed organization source packet.
WORKFLOW_HASHES = {'auto-merge-to-develop.yml': 'a28d9b92576590903290809643f21c93f680a6b2a1a8913d6c6e2fed89993de0',
 'cla.yml': '55b422a674acb918d247b3a025bf413fe751de16b85f5f06f1251331c4d98c06',
 'import-smoke.yml': 'df8fb3d63e91612353b3fcbfcaf6f0e43d7c0102f799b48e82d8a47e32956f06',
 'promote-develop-to-main-on-tag.yml': '1e3cec556f96612ff987f1bc2969dd145f85ebfff48297a3bf3adccd0b8c0c69',
 'pytest-matrix.yml': 'e822cffc869bde67a19b97755aa5844c2c83ee717c168540562ee0984a72f0ae',
 'quality-audit.yml': 'f44a2e6b5c479c2975d1cedf66738fdbf402a74cf1d8e26340bb9895524e7b4a',
 'rtd-sphinx-build.yml': '51be02f591beeeb5398b6447a7c26f0959e5487cad5b974bf62d2cf56fd51b5d',
 'runner-admission.yml': 'e4eb6c5cc5aedd8a460380f796047c2ea33a446846235001355697350d36c915'}


def qualify_workflows(groups, api, *, workflow_hashes=None, native_workflows=None) -> dict:
    hashes = WORKFLOW_HASHES if workflow_hashes is None else workflow_hashes
    names_expected = NATIVE_WORKFLOWS if native_workflows is None else native_workflows
    result = {"expected": [], "violations": [], "unknown": [], "source": []}
    restricted = [g for g in groups if g.get("restricted_to_workflows") is True]
    if not restricted:
        return result
    revisions = set()
    for group in restricted:
        refs = group.get("selected_workflows")
        if not isinstance(refs, list) or len(refs) != len(names_expected):
            result["violations"].append("reviewed workflow selection must contain exactly seven definitions")
            continue
        names = set()
        for ref in refs:
            m = re.fullmatch(r"scitex-ai/\.github/\.github/workflows/([A-Za-z0-9_-]+\.yml)@([a-f0-9]{40})", ref) if isinstance(ref, str) else None
            if not m:
                result["violations"].append("reviewed workflow selection has a mutable or foreign revision")
                continue
            names.add(m[1])
            revisions.add(m[2])
        if names != set(names_expected):
            result["violations"].append("reviewed workflow definitions differ from the organization contract")
    if result["violations"] or len(revisions) != 1:
        if len(revisions) != 1:
            result["violations"].append("reviewed workflows must share one immutable revision")
        return result
    revision = next(iter(revisions))
    for name, expected in hashes.items():
        payload = api(f"repos/scitex-ai/.github/contents/.github/workflows/{name}?ref={revision}")
        try:
            if payload.get("type") != "file" or payload.get("encoding") != "base64":
                raise ValueError
            encoded = payload["content"]
            if not isinstance(encoded, str) or len(encoded) > 256 * 1024:
                raise ValueError
            body = base64.b64decode("".join(encoded.split()), validate=True)
        except (AttributeError, KeyError, TypeError, ValueError):
            result["unknown"].append(f"reviewed workflow bytes unavailable: {name}")
            continue
        actual = hashlib.sha256(body).hexdigest()
        result["source"].append({"workflow": name, "revision": revision, "sha256": actual})
        if actual != expected:
            result["violations"].append(f"reviewed workflow bytes changed: {name}")
    if not hashes:
        result["unknown"].append("reviewed workflow byte contract absent")
    if not result["unknown"] and not result["violations"]:
        result["expected"] = [f"scitex-ai/.github/.github/workflows/{name}@{revision}" for name in names_expected]
    return result
