"""The normal Actions variable API, with visible failure and readback."""
import json
import re
import subprocess


def _invoke(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=7)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Actions variable API unavailable") from None


def _decode(stdout):
    try:
        return json.loads(stdout)
    except (ValueError, TypeError):
        return None


def set_runs_on(repo: str, name: str, value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo) or repo.split("/")[1] in (".", ".."):
        raise ValueError("invalid Actions repository")
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,99}", name):
        raise ValueError("invalid Actions variable name")
    collection = f"repos/{repo}/actions/variables"
    target = collection + "/" + name
    current = _invoke(["gh", "api", target])
    payload = _decode(current.stdout)
    if current.returncode == 0 and isinstance(payload, dict) and payload.get("name") == name:
        method, endpoint = "PATCH", target
    elif current.returncode != 0 and isinstance(payload, dict) and payload.get("status") in ("404", 404):
        method, endpoint = "POST", collection
    else:
        raise ValueError("Actions variable lookup unavailable; no write attempted")
    changed = _invoke(["gh", "api", endpoint, "--method", method,
                       "-f", f"name={name}", "-f", f"value={value}"])
    if changed.returncode:
        raise ValueError("Actions variable write failed")
    confirmed = _invoke(["gh", "api", target])
    result = _decode(confirmed.stdout)
    if confirmed.returncode or not isinstance(result, dict) or result.get("name") != name or result.get("value") != value:
        raise ValueError("Actions variable readback did not confirm destination")
