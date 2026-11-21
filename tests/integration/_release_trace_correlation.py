"""Bounded positive correlation, never process authentication or a diagnosis."""

import json
import re

_LIMIT = "Git 2.43.0 trace v3 SID low32 correlation only; not authenticated child or root cause"
_COMPONENT = re.compile(
    r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-(?:H[0-9a-f]{8}|Localhost)-P([0-9a-f]{8})\Z"
)


def _unknown(reason):
    return {"state": "unknown", "reason": reason, "limit": _LIMIT}


def _trace_pid(command, trace):
    if not isinstance(trace, str) or len(trace) > 8192 or not trace.endswith("\n"):
        return None
    try:
        events = [json.loads(line) for line in trace.splitlines()]
    except (ValueError, RecursionError):
        return None
    if any(not isinstance(event, dict) for event in events):
        return None
    starts = [event for event in events
              if event.get("event") == "start" and event.get("argv") == command]
    if len(starts) != 1 or not isinstance(starts[0].get("sid"), str):
        return None
    sid = starts[0]["sid"]
    versions = [event for event in events
                if event.get("event") == "version" and event.get("sid") == sid]
    if len(versions) != 1 or versions[0].get("exe") != "2.43.0" or versions[0].get("evt") != "3":
        return None
    match = _COMPONENT.fullmatch(sid.rsplit("/", 1)[-1])
    if match is None:
        return None
    pid = int(match[1], 16)
    return pid if pid else None


def _candidate_count(pid, observation):
    if not isinstance(observation, dict):
        return None
    samples = observation.get("samples")
    if not isinstance(samples, list) or len(samples) > 24:
        return None
    identities = set()
    count = 0
    for row in samples:
        if not isinstance(row, dict):
            return None
        if row.get("state") != "observed":
            continue
        child = row.get("child")
        if not isinstance(child, dict):
            return None
        actual, birth = child.get("pid"), child.get("birth_ticks")
        if type(actual) is not int or actual != pid or type(birth) is not int or birth < 0:
            return None
        identities.add((actual, birth))
        count += 1
    return count if len(identities) == 1 else None


def correlate_git_trace_candidate(command, trace, observation):
    """Join one known-version start event to consistent numeric candidates.

    Unknown versions, partial/malformed traces and mixed candidate identities
    remain unknown. No trace text, SID, arguments or paths enter the result.
    """
    pid = _trace_pid(command, trace)
    if pid is None:
        return _unknown("no unique supported complete Git start/version evidence")
    count = _candidate_count(pid, observation)
    if count is None:
        return _unknown("no consistent bounded candidate match")
    return {"state": "correlated", "git_pid_low32": pid,
            "matching_candidate_samples": count, "limit": _LIMIT}
