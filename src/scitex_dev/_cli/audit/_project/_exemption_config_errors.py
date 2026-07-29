# -*- coding: utf-8 -*-
"""The shared `audit.exemptions` CONFIG-ERROR arm.

A rejected exemption exempts NOTHING — the site still fires — and a malformed
`exemptions:` block costs every rule its exemptions. Either way the author
wrote something that did not take effect, so the auditor reports it at `E`
against the config file rather than letting it read as a quiet pass.

Four checkers (PS-220 / PS-222 / PS-223 / PS-224) carried near-identical
copies of this loop, and the copies had already drifted: three filtered
notices with a bare `notice.startswith("PS-22x")` — which silently DROPS the
block-level notice, i.e. drops the report of a silent drop — and PS-224 had no
arm at all despite its docstring promising one. One implementation, so the
next fix lands in one place.

The `emit` callable is the seam: each checker passes a closure carrying its
own `Violation` construction and per-finding severity override, which is the
only part that legitimately differs between them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .._config import exemption_notice_applies, format_exemption_notice

#: Where the config errors are reported — the file the author actually edited.
CONFIG_REL = ".scitex/dev/config.yaml"


def report_exemption_config_errors(
    repo: Path,
    config,
    rule: str,
    emit: Callable[[str, str], object],
) -> None:
    """Hand every `audit.exemptions` notice that ``rule`` owns to ``emit``.

    Parameters
    ----------
    repo : Path
        Repository root; the finding's location is ``<repo>/.scitex/dev/config.yaml``.
    config : ProjectConfig | None
        Pre-loaded project config. A config without ``exemption_errors`` (a
        stub, or ``None``) simply yields nothing.
    rule : str
        The reporting rule code. Entry-level notices are matched against it;
        BLOCK-level notices are reported by EVERY rule, since a malformed
        block dropped every rule's exemptions.
    emit : Callable[[str, str], object]
        ``emit(where, detail)`` — the caller's violation constructor, which
        owns the per-finding severity.
    """
    for notice in tuple(getattr(config, "exemption_errors", ()) or ()):
        if not exemption_notice_applies(notice, rule):
            continue
        emit(str(repo / CONFIG_REL), format_exemption_notice(notice, rule))


__all__ = ["CONFIG_REL", "report_exemption_config_errors"]

# EOF
