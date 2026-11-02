"""Project exact proposed current-main bytes into historical test contexts.

Historical fixture archives remain unchanged. These explicit hypothetical
projections are neither API observations nor source-admission decisions.
"""

import copy
import gzip
import json
import re
from pathlib import Path

CENTRAL = "repos/scitex-ai/.github/"
MATRIX = "contents/.github/workflows/ci-sif-matrix.yml?ref="


def candidate_publisher():
    """Read the single explicit candidate packet shared by policy tests."""
    return json.loads(gzip.decompress((
        Path(__file__).parent / "fixtures/dev-protected-release-publisher.json.gz"
    ).read_bytes()))


def compose_candidate_central_matrix(responses, *, main_revision=None):
    """Project only the matrix body at this context's resolved current main.

    Never rewrite branch/protection evidence, other workflows, or immutable
    historical refs. A context without a resolved main must supply its own
    fixture's explicit main revision; there is no last-response inference.
    """
    candidate = candidate_publisher()
    source_main = candidate["source_revisions"]["scitex-ai/.github"]
    if main_revision is None:
        main_revision = responses[CENTRAL + "branches/main"]["commit"]["sha"]
    if not isinstance(main_revision, str) or not re.fullmatch(r"[a-f0-9]{40}", main_revision):
        raise ValueError("The replay needs its explicit resolved current main")
    from scitex_dev.ci.runner._policy_contract import IMMUTABLE_REVISIONS
    if main_revision in IMMUTABLE_REVISIONS.values():
        raise ValueError("A candidate main cannot replace an immutable fixture revision")
    result = copy.deepcopy(responses)
    result[CENTRAL + MATRIX + main_revision] = copy.deepcopy(
        candidate["responses"][CENTRAL + MATRIX + source_main]
    )
    return result


def compose_candidate_dev_publisher(responses, *, include_dev=True, include_matrix=True):
    """Compose finite Dev responses and the one exact current-main dependency."""
    result = copy.deepcopy(responses)
    if include_dev:
        result.update({
            key: copy.deepcopy(value)
            for key, value in candidate_publisher()["responses"].items()
            if key.startswith("repos/scitex-ai/scitex-dev/")
        })
    if include_matrix:
        result = compose_candidate_central_matrix(result)
    return result
