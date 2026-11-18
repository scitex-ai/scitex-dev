"""Constant, bounded observations for the reviewed JavaScript callee control."""

import json

PREFIX = "dev-ci-callee-stage: "
STAGES = ("javascript-entered", "contract-loaded", "invocation-evaluated")
CAPTURE_LIMIT = 512


def traced_callee_source(contract, invocation):
    """Observe synchronous progress without changing the contract or invocation."""

    def marker(stage):
        return "process.stderr.write(" + json.dumps(PREFIX + stage + "\n") + ");\n"

    return (
        marker(STAGES[0])
        + contract
        + "\n"
        + marker(STAGES[1])
        + invocation
        + "\n"
        + marker(STAGES[2])
    )


def captured_callee_stages(stderr):
    """Return only complete known lines in the first 512 captured bytes/chars.

    Absence is not evidence that execution never reached a stage. The final
    marker observes synchronous evaluation, not asynchronous or process success.
    """
    if isinstance(stderr, bytes):
        allowed = {(PREFIX + stage).encode("ascii"): stage for stage in STAGES}
        newline = b"\n"
    elif isinstance(stderr, str):
        allowed = {PREFIX + stage: stage for stage in STAGES}
        newline = "\n"
    else:
        return []
    lines = stderr[:CAPTURE_LIMIT].split(newline)[:-1]
    return [allowed[line] for line in lines if line in allowed]
