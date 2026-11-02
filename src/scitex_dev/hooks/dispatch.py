"""JSON stdin bridge for Claude and Hermes shell hooks."""

import argparse
import json
import sys

import scitex_logging as slogging

from ._dispatch import dispatch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True)
    parser.add_argument(
        "--rule",
        dest="rule_ids",
        action="append",
        default=None,
        help="Select exact executable rule IDs of the provider (repeatable).",
    )
    args = parser.parse_args()
    try:
        findings = dispatch(
            json.load(sys.stdin), provider=args.provider, rule_ids=args.rule_ids
        )
    except (ValueError, OSError, TypeError) as exc:
        findings = [f"Cannot verify hook payload ({type(exc).__name__})"]
    for finding in findings:
        slogging.getLogger(__name__).error(finding)
    return 2 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
