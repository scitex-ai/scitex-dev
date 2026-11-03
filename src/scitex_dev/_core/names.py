"""Strict distribution identities shared by metadata, setup and host adapters."""

from packaging.utils import InvalidName, canonicalize_name

__all__ = ["normalize_distribution_name"]


def normalize_distribution_name(name: str) -> str:
    """Validate an ASCII distribution identity and return its PEP 503 form.

    Reject surrounding whitespace explicitly: older supported packaging releases
    accepted a final newline in their validation regex. This is an identity,
    not a path, requirement expression or URL.
    """
    if not isinstance(name, str) or not name or not name.isascii() or name != name.strip():
        raise ValueError("invalid distribution name")
    try:
        return str(canonicalize_name(name, validate=True))
    except InvalidName as exc:
        raise ValueError("invalid distribution name") from exc
