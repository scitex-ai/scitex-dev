"""Read-only health checks for PEP 610 editable source directories."""

from __future__ import annotations

import json
import stat
from importlib.metadata import distributions as installed_distributions
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname


def _source_status(direct: object) -> tuple[str, str] | None:
    if not isinstance(direct, dict):
        return "skip", "cannot inspect editable metadata: expected an object"
    directory = direct.get("dir_info", {})
    if not isinstance(directory, dict):
        return "skip", "cannot inspect editable metadata: invalid dir_info"
    if directory.get("editable") is not True:
        return None
    url = direct.get("url")
    if not isinstance(url, str):
        return "skip", "cannot inspect editable metadata: missing source URL"
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "file"
            or parts.netloc not in ("", "localhost")
            or parts.query
            or parts.fragment
        ):
            return "skip", "editable directory unverified: unsupported source URL"
        source = Path(url2pathname(parts.path))
        if not source.is_absolute():
            return "skip", "editable directory unverified: source URL is not absolute"
        metadata = source.stat()
    except (FileNotFoundError, NotADirectoryError):
        return "fail", f"editable source directory is missing: {source}"
    except (OSError, ValueError) as error:
        return "skip", f"editable directory unverified: {type(error).__name__}"
    if not stat.S_ISDIR(metadata.st_mode):
        return "fail", f"editable source is not a directory: {source}"
    return "ok", f"editable source directory exists (imports not checked): {source}"


def check_editable_installs(distributions=None) -> list[dict]:
    """Inspect current-environment metadata without importing or fixing packages."""
    if distributions is None:
        distributions = installed_distributions()
    results = []
    for distribution in distributions:
        label = f"Editable {distribution.metadata.get('Name', 'unknown distribution')}"
        try:
            text = distribution.read_text("direct_url.json")
            if text is None:
                continue
            verdict = _source_status(json.loads(text))
        except (OSError, ValueError) as error:
            verdict = (
                "skip",
                f"cannot inspect editable metadata: {type(error).__name__}",
            )
        if verdict is not None:
            status, detail = verdict
            results.append({"check": label, "status": status, "detail": detail})
    return sorted(results, key=lambda row: row["check"])
