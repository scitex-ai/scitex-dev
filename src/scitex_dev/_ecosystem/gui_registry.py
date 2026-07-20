#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/_ecosystem/gui_registry.py

"""SciTeX leaf-package browser-GUI port registry -- *data only*.

This module is the **single source of truth (SSOT)** for the ports that
each leaf package's browser GUI binds to. scitex-dev owns this registry
so the ecosystem can migrate every default into the reserved local-port
scheme and fan the assignments back out to each leaf.

Each :class:`GuiSurface` records TWO ports:

- ``actual_port`` -- what the leaf GUI binds TODAY (what
  ``scitex-dev ecosystem gui open`` uses right now).
- ``target_port`` -- the leaf's assigned slot in the reserved scheme
  (the SSOT-owned destination).

The reserved local-port scheme
------------------------------
The ``3129X`` block (31290-31299) is **full** and is shared with
non-GUI SciTeX services, so the GUI registry is NOT free to pick any
``3129X`` port -- picking a taken one is a real runtime collision. The
full reservation set is encoded in :data:`RESERVED_PORTS` (port ->
owner) precisely so a future edit cannot silently re-collide: the
auditor and the registry-invariants test check every ``target_port``
against it.

Because ``3129X`` is full, GUI surfaces that do not already own a slot
there overflow into the next block, ``3130X`` (31300+). ``scitex-cards``
serves the todo board and shares slot ``31299`` with it; ``live-paper``
is the first ``3130X`` overflow entry at ``31300`` (its ``actual_port``
stays ``8765`` so the launcher keeps opening the live GUI until the
migration lands).

History: an earlier draft seeded cards->31291 and live-paper->31292;
both COLLIDED with existing services (crossref-local binds 31291,
openalex-local binds 31292), so they were corrected to 31299/31300.
That collision is the exact reason :data:`RESERVED_PORTS` encodes the
non-GUI reservations too.

Leaf fan-out is a **tracked follow-up**, NOT done by this module:
updating each leaf's own manifest / CLI default to bind its assigned
target -- and fixing figrecipe's manifest which wrongly advertises
``5050`` while it actually binds ``31296`` -- happens leaf-by-leaf.
Until then this registry stays the compiled-from-source truth of the
*actual* binds.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "GuiSurface",
    "GUI_SURFACES",
    "gui_surfaces",
    "RESERVED_PORTS",
    "reserved_ports",
]


@dataclass(frozen=True)
class GuiSurface:
    """One leaf package's browser-GUI surface.

    ``actual_port`` is the port the GUI binds today; ``target_port`` is
    its assigned slot in the scitex-dev-owned reserved scheme. ``path``
    is the URL path the GUI serves its entry page at (default ``/``).
    """

    package: str
    actual_port: int
    target_port: int
    path: str = "/"

    def url(self, host: str = "localhost", use_target: bool = False) -> str:
        """Return the ``http://<host>:<port><path>`` URL for this surface.

        Uses ``actual_port`` by default (what is live today); pass
        ``use_target=True`` to render the future assignment.
        """
        port = self.target_port if use_target else self.actual_port
        return f"http://{host}:{port}{self.path}"


# The FULL reserved local-port scheme: port -> owning package. GUI
# surfaces are a SUBSET (storage/figrecipe/scholar/writer/cards/
# live-paper); the non-GUI reservations (crossref/openalex/audio/hub)
# are recorded here too so the auditor knows those ports are TAKEN and
# a future GUI assignment cannot re-collide with them. Grounded in each
# owner's source (e.g. crossref-local binds 31291, openalex-local 31292,
# scitex-audio 31293, scitex-storage _gui_cmd FIXED_PORT=31290). 31294/
# 31295 are scitex-hub staging/dev. GUI slots: figrecipe 31296, scholar
# 31297, writer 31298, cards/todo 31299; live-paper 31300 is the first
# 3130X overflow because 3129X is full.
RESERVED_PORTS: dict[int, str] = {
    31290: "scitex-storage",
    31291: "crossref-local",
    31292: "openalex-local",
    31293: "scitex-audio",
    31294: "scitex-hub-staging",
    31295: "scitex-hub-dev",
    31296: "figrecipe",
    31297: "scitex-scholar",
    31298: "scitex-writer",
    31299: "scitex-cards",
    31300: "scitex-live-paper",
}


# Compiled from the leaf source manifests (not the advertised values --
# figrecipe advertises 5050 but binds 31296). Order is display order.
# Each target_port MUST match its RESERVED_PORTS owner (enforced by the
# registry-invariants test and `ecosystem gui audit`).
GUI_SURFACES: tuple[GuiSurface, ...] = (
    GuiSurface("scitex-cards", actual_port=8051, target_port=31299),
    GuiSurface("scitex-live-paper", actual_port=8765, target_port=31300),
    GuiSurface("scitex-storage", actual_port=31290, target_port=31290),
    GuiSurface("figrecipe", actual_port=31296, target_port=31296),
    GuiSurface("scitex-scholar", actual_port=31297, target_port=31297),
    GuiSurface("scitex-writer", actual_port=31298, target_port=31298),
)


def gui_surfaces() -> list[GuiSurface]:
    """Return the registered leaf GUI surfaces as a list."""
    return list(GUI_SURFACES)


def reserved_ports() -> dict[int, str]:
    """Return the full reserved local-port scheme (port -> owner)."""
    return dict(RESERVED_PORTS)


# EOF
