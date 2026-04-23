"""POC: verifies `claude -p` works against either backend (host or docker)
and that tool_use extraction yields paths.

Run:
    python -m scitex_dev._agentic_testing_poc --backend host
    python -m scitex_dev._agentic_testing_poc --backend docker
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from ._agentic_testing import DEFAULT_MODEL, extract_viewed_paths, get_runner


def _cost_from(result: dict) -> float | None:
    for key in ("total_cost_usd", "cost_usd"):
        if key in result and isinstance(result[key], (int, float)):
            return float(result[key])
    usage = result.get("usage") or {}
    if isinstance(usage, dict):
        for key in ("total_cost_usd", "cost_usd"):
            if key in usage and isinstance(usage[key], (int, float)):
                return float(usage[key])
    return None


def _cache_creation(result: dict) -> int | None:
    usage = result.get("usage") or {}
    if isinstance(usage, dict):
        v = usage.get("cache_creation_input_tokens")
        if isinstance(v, int):
            return v
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--backend",
        choices=["host", "docker"],
        default=None,
        help="Override SCITEX_DEV_AGENTIC_BACKEND. Default: host.",
    )
    ap.add_argument("--prompt", default="hello")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    runner = get_runner(args.backend)
    print(
        f"Using backend: {args.backend or 'host (default)'} ({type(runner).__name__})",
        file=sys.stderr,
    )
    try:
        t0 = time.monotonic()
        result = runner.run(args.prompt, model=args.model)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        runner.close()
        return 2

    print("=== raw claude -p JSON (truncated) ===")
    print(json.dumps(result, indent=2)[:800])
    print("=== extracted viewed paths ===")
    print(extract_viewed_paths(result))

    cost = _cost_from(result)
    cache_create = _cache_creation(result)
    print("=== metrics ===")
    print(f"duration_ms           : {elapsed_ms}")
    print(f"cost_usd              : {cost!r}")
    print(f"cache_creation_tokens : {cache_create!r}")

    runner.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
