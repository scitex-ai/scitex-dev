#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_ecosystem/_exemption_census.py

"""Every audit exemption in the fleet, in one place, WITH ITS BLIND SPOT NAMED.

WHY THIS EXISTS. Operator, 2026-08-16: 「例外として leaf 固有の workflow を
認める; 例外はこちらで把握できるようにする」 — leaf-specific workflows are
permitted AS EXCEPTIONS, and the exceptions must be visible centrally.

The exemption mechanism satisfies the first half already: each is declared
per-file in that repo's own ``.scitex/dev/config.yaml`` with a mandatory
written reason. It does NOT satisfy the second half, because those files live
in ~70 separate repositories. Nobody could answer "how many exemptions exist,
where, and why" without opening 70 files, so in practice nobody asks — and an
exception nobody can see is an exception that never gets retired.

THE FAILURE THIS MODULE IS BUILT TO AVOID
------------------------------------------
A census that quietly skips what it cannot read REPORTS A SMALLER NUMBER THAN
THE TRUTH, and reports it in the reassuring direction. A repo that is not
checked out locally has no config to read; treating that as "no exemptions"
would mean the fleet always looks tidier than it is, and the gap would widen
silently as checkouts go missing.

So the result is THREE-VALUED and the unreadable set is returned as data
rather than dropped:

    exemptions   what was actually found and read
    unreadable   packages whose config could NOT be consulted, with why
    clean        packages read successfully that declare none

`unreadable` is not an error path. It is a first-class part of the answer, and
a caller that prints the total without it is publishing a number it cannot
support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ExemptionRow",
    "ExemptionCensus",
    "collect_exemptions",
]


@dataclass(frozen=True)
class ExemptionRow:
    """One exemption, with the package it belongs to attached."""

    package: str
    rule: str
    path: str
    line: int
    reason: str


@dataclass(frozen=True)
class ExemptionCensus:
    """The whole answer, including what could not be answered.

    `total_declared` deliberately does NOT try to estimate the unreadable
    packages. An estimate here would be a guess wearing a number's clothes;
    the honest report is "N found across M packages, K packages unread".
    """

    exemptions: tuple[ExemptionRow, ...] = ()
    clean: tuple[str, ...] = ()
    unreadable: tuple[tuple[str, str], ...] = field(default=())

    @property
    def total_declared(self) -> int:
        return len(self.exemptions)

    @property
    def is_complete(self) -> bool:
        """True only when every package was actually consulted.

        Callers should print a warning when this is False rather than
        presenting `total_declared` as the fleet's exemption count.
        """
        return not self.unreadable


def collect_exemptions(
    ecosystem: dict,
    *,
    load_config,
    packages: list[str] | None = None,
) -> ExemptionCensus:
    """Read every selected package's declared exemptions.

    `load_config` is injected rather than imported so a test can hand in a
    real function over a real temp tree without patching module globals —
    and so this module does not depend on the audit CLI package.
    """
    selected = sorted(packages) if packages else sorted(ecosystem)

    rows: list[ExemptionRow] = []
    clean: list[str] = []
    unreadable: list[tuple[str, str]] = []

    for pkg in selected:
        # `is None`, NOT falsiness. An entry of `{}` is REGISTERED BUT
        # INCOMPLETE, which is a different problem from being unregistered:
        # one is fixed by adding the package, the other by completing its row.
        # `if not entry` reports the second as the first, and a caller acting
        # on that message would go add a package that is already there.
        #
        # Caught by test_a_registry_entry_without_local_path_is_unreadable on
        # the first run of this module. It is the same emptiness-collapse this
        # file's docstring warns about, committed inside the guard against it.
        entry = ecosystem.get(pkg)
        if entry is None:
            unreadable.append((pkg, "not in the ECOSYSTEM registry"))
            continue

        local = entry.get("local_path")
        if not local:
            unreadable.append((pkg, "registry entry declares no local_path"))
            continue

        repo = Path(str(local)).expanduser()
        if not repo.is_dir():
            # NOT "no exemptions". The checkout is absent, so the question
            # was never asked of this package.
            unreadable.append((pkg, f"not checked out at {repo}"))
            continue

        try:
            config = load_config(repo)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            unreadable.append((pkg, f"config unreadable: {exc}"))
            continue

        declared = getattr(config, "exemptions", ()) or ()
        if not declared:
            clean.append(pkg)
            continue

        for ex in declared:
            rows.append(
                ExemptionRow(
                    package=pkg,
                    rule=ex.rule,
                    path=ex.path,
                    line=ex.line,
                    reason=ex.reason,
                )
            )

    return ExemptionCensus(
        exemptions=tuple(rows),
        clean=tuple(clean),
        unreadable=tuple(unreadable),
    )


# EOF
