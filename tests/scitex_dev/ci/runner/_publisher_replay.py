"""Compose the explicit candidate Dev publisher into historical host replays.

The historical fixture files remain unchanged. This is a hypothetical source
projection for tests, never an API observation or source-admission decision.
"""

import copy
import gzip
import json
from pathlib import Path


def compose_candidate_dev_publisher(responses):
    """Replace only the Dev publisher's own repository responses."""
    candidate = json.loads(gzip.decompress((
        Path(__file__).parent / "fixtures/dev-protected-release-publisher.json.gz"
    ).read_bytes()))
    result = copy.deepcopy(responses)
    result.update({
        key: copy.deepcopy(value)
        for key, value in candidate["responses"].items()
        if key.startswith("repos/scitex-ai/scitex-dev/")
    })
    return result
