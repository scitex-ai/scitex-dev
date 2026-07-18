#!/usr/bin/env python3
# Timestamp: 2026-07-06
# File: scitex_dev/_ecosystem/_drift_report/_sac.py

"""``sac versions --json`` parse + fold + fail-open collection.

The ``sac versions --json`` verb (scitex-agent-container) emits a flat
JSON list of ``{agent, layer, image, package, version, source}`` where
``layer ∈ {"base-image", "agent-overlay"}`` and
``source ∈ {"manifest", "live"}``. It backs layers 5 (container base
image) and 6 (agent overlay).

The verb is being built in parallel and may not exist yet, and the drift
report may run from a host without ``sac`` at all — so every entry point
here degrades GRACEFULLY (returns ``None`` + a reason string; never
raises). :func:`parse_sac_output` and :func:`fold_sac_versions` are pure
(unit-tested against a synthetic fixture of that exact shape);
:func:`collect_sac_rows` wraps them behind a test-fakable subprocess
runner.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Callable, Iterable

from ._model import SacFold


def parse_sac_output(stdout: str | bytes | None) -> list[dict] | None:
    """Parse ``sac versions --json`` stdout into a list of row dicts.

    Tolerates a bare JSON array or a ``{"versions": [...]}`` /
    ``{"rows": [...]}`` envelope. Returns ``None`` (never raises) when
    the text is missing / not JSON / not a list-of-objects.
    """
    if stdout is None:
        return None
    if isinstance(stdout, bytes):
        try:
            stdout = stdout.decode("utf-8")
        except UnicodeDecodeError:
            return None
    text = stdout.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(data, dict):
        for key in ("versions", "rows", "results", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            return None
    if not isinstance(data, list):
        return None
    return [row for row in data if isinstance(row, dict)]


def fold_sac_versions(rows: Iterable[dict] | None) -> SacFold:
    """Fold the flat rows into a :class:`SacFold`.

    Malformed / partial rows (missing package or version, unknown layer)
    are skipped so one bad row never breaks the fold.
    """
    base_by_image: dict[str, dict[str, str]] = {}
    overlay_by_agent: dict[str, dict[str, str]] = {}
    agent_image: dict[str, str] = {}

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        layer = row.get("layer")
        package = row.get("package")
        version = row.get("version")
        agent = row.get("agent")
        image = row.get("image")
        if not package or version is None:
            continue
        version = str(version)
        if layer == "base-image":
            if image:
                base_by_image.setdefault(image, {})[package] = version
                if agent:
                    agent_image.setdefault(agent, image)
        elif layer == "agent-overlay":
            if agent:
                overlay_by_agent.setdefault(agent, {})[package] = version
                if image:
                    agent_image.setdefault(agent, image)

    return SacFold(
        base_by_image=base_by_image,
        overlay_by_agent=overlay_by_agent,
        agent_image=agent_image,
    )


def collect_sac_rows(
    *,
    runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> tuple[list[dict] | None, str]:
    """Shell out to ``sac versions --json`` and parse it — fail-open.

    Returns ``(rows, note)``. ``rows`` is ``None`` on ANY failure and
    ``note`` carries the reason string surfaced in the report:

    * ``sac`` not on PATH,
    * nonzero exit / unknown verb → ``"unavailable (sac versions --json
      not present)"``,
    * unparseable output.

    The argv is list-form (never ``shell=True``). When a ``runner`` is
    injected the PATH probe is skipped (tests own the outcome).
    """
    run = runner or _default_sac_runner
    if runner is None and which("sac") is None:
        return None, "unavailable (sac not on PATH)"
    try:
        code, out, _err = run(["sac", "versions", "--json"])
    except Exception as exc:  # noqa: BLE001 — best-effort external probe
        return None, (
            f"unavailable (sac versions --json failed: {exc.__class__.__name__})"
        )
    if code != 0:
        return None, "unavailable (sac versions --json not present)"
    rows = parse_sac_output(out)
    if rows is None:
        return None, "unavailable (sac versions --json output not parseable)"
    return rows, ""


def _default_sac_runner(args: list[str]) -> tuple[int, str, str]:
    """Real ``sac`` invocation (list-form argv, never ``shell=True``)."""
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


# EOF
