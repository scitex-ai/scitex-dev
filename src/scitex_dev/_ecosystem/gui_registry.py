#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/_ecosystem/gui_registry.py

"""SciTeX leaf-package browser-GUI port registry -- *data only*.

This module is the **single source of truth (SSOT)** for the ports that
each leaf package's browser GUI binds to. scitex-dev owns this registry
so the ecosystem can migrate every default into a contiguous, reserved
``3129X`` block and fan the assignments back out to each leaf.

Each :class:`GuiSurface` records TWO ports:

- ``actual_port`` -- what the leaf GUI binds TODAY (what
  ``scitex-dev ecosystem gui open`` uses right now).
- ``target_port`` -- the leaf's assigned slot in the ``3129X`` block
  (the SSOT-owned destination).

Four surfaces already live in the block (storage/figrecipe/scholar/writer);
the two out-of-block ones (cards/todo-board and live-paper) are assigned
``31291`` / ``31292`` here as their migration targets.

Leaf fan-out is a **tracked follow-up**, NOT done by this module: updating
each leaf's own manifest / CLI default to bind its ``3129X`` target -- and
fixing figrecipe's manifest which wrongly advertises ``5050`` while it
actually binds ``31296`` -- happens leaf-by-leaf. Until then this registry
stays the compiled-from-source truth of the *actual* binds.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["GuiSurface", "GUI_SURFACES", "gui_surfaces"]


@dataclass(frozen=True)
class GuiSurface:
    """One leaf package's browser-GUI surface.

    ``actual_port`` is the port the GUI binds today; ``target_port`` is
    its assigned slot in the scitex-dev-owned ``3129X`` block. ``path``
    is the URL path the GUI serves its entry page at (default ``/``).
    """

    package: str
    actual_port: int
    target_port: int
    path: str = "/"

    def url(self, host: str = "localhost", use_target: bool = False) -> str:
        """Return the ``http://<host>:<port><path>`` URL for this surface.

        Uses ``actual_port`` by default (what is live today); pass
        ``use_target=True`` to render the future ``3129X`` assignment.
        """
        port = self.target_port if use_target else self.actual_port
        return f"http://{host}:{port}{self.path}"


# Compiled from the leaf source manifests (not the advertised values --
# figrecipe advertises 5050 but binds 31296). Order is display order.
GUI_SURFACES: tuple[GuiSurface, ...] = (
    GuiSurface("scitex-cards", actual_port=8051, target_port=31291),
    GuiSurface("scitex-live-paper", actual_port=8765, target_port=31292),
    GuiSurface("scitex-storage", actual_port=31290, target_port=31290),
    GuiSurface("figrecipe", actual_port=31296, target_port=31296),
    GuiSurface("scitex-scholar", actual_port=31297, target_port=31297),
    GuiSurface("scitex-writer", actual_port=31298, target_port=31298),
)


def gui_surfaces() -> list[GuiSurface]:
    """Return the registered leaf GUI surfaces as a list."""
    return list(GUI_SURFACES)


# EOF
