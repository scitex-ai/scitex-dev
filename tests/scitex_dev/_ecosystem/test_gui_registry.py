#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the leaf-GUI port-registry SSOT (scitex_dev._ecosystem.gui_registry)."""

from __future__ import annotations

from scitex_dev._ecosystem.gui_registry import (
    GUI_SURFACES,
    RESERVED_PORTS,
    GuiSurface,
    gui_surfaces,
)


def test_gui_surfaces_has_six_entries():
    # Arrange
    # Act
    surfaces = gui_surfaces()
    # Assert
    assert len(surfaces) == 6


def test_gui_surfaces_returns_list_of_gui_surface():
    # Arrange
    # Act
    surfaces = gui_surfaces()
    # Assert
    assert all(isinstance(s, GuiSurface) for s in surfaces)


def test_url_uses_actual_port_by_default():
    # Arrange
    surface = GuiSurface("demo", actual_port=8051, target_port=31291)
    # Act
    url = surface.url()
    # Assert
    assert url == "http://localhost:8051/"


def test_url_uses_target_port_when_requested():
    # Arrange
    surface = GuiSurface("demo", actual_port=8051, target_port=31291)
    # Act
    url = surface.url(use_target=True)
    # Assert
    assert url == "http://localhost:31291/"


def test_url_honours_custom_host():
    # Arrange
    surface = GuiSurface("demo", actual_port=8051, target_port=31291)
    # Act
    url = surface.url(host="example.org")
    # Assert
    assert url == "http://example.org:8051/"


def test_cards_target_port_is_31299():
    # Arrange
    cards = next(s for s in GUI_SURFACES if s.package == "scitex-cards")
    # Act
    target = cards.target_port
    # Assert
    assert target == 31299


def test_live_paper_target_port_is_31300_overflow():
    # Arrange
    live_paper = next(s for s in GUI_SURFACES if s.package == "scitex-live-paper")
    # Act
    target = live_paper.target_port
    # Assert
    assert target == 31300


def test_live_paper_actual_port_stays_8765():
    # Arrange
    live_paper = next(s for s in GUI_SURFACES if s.package == "scitex-live-paper")
    # Act
    actual = live_paper.actual_port
    # Assert
    assert actual == 8765


def test_every_target_is_reserved_to_its_own_package():
    # Arrange
    surfaces = gui_surfaces()
    # Act
    mismatched = [s for s in surfaces if RESERVED_PORTS.get(s.target_port) != s.package]
    # Assert
    assert mismatched == []


def test_no_two_surfaces_share_a_target_port():
    # Arrange
    targets = [s.target_port for s in gui_surfaces()]
    # Act
    duplicated = len(targets) != len(set(targets))
    # Assert
    assert not duplicated


def test_cards_and_live_paper_targets_no_longer_collide_with_relays():
    # Arrange (31291 crossref-local / 31292 openalex-local are NOT GUI slots)
    gui_targets = {s.target_port for s in gui_surfaces()}
    # Act
    collisions = gui_targets & {31291, 31292}
    # Assert
    assert collisions == set()
