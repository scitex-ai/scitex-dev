"""JSON stdin bridge for Claude and Hermes shell hooks."""

import argparse
import json
import sys

import scitex_logging as slogging

from ._dispatch import dispatch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True)
    args = parser.parse_args()
    try:
        findings = dispatch(json.load(sys.stdin), provider=args.provider)
    except (ValueError, OSError, TypeError) as exc:
        findings = [f"Cannot verify hook payload ({type(exc).__name__})"]
    for finding in findings:
        slogging.getLogger(__name__).error(finding)
    return 2 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
