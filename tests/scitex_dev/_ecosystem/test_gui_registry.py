#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the leaf-GUI port-registry SSOT (scitex_dev._ecosystem.gui_registry)."""

from __future__ import annotations

from scitex_dev._ecosystem.gui_registry import GUI_SURFACES, GuiSurface, gui_surfaces


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


def test_cards_target_port_in_3129x_block():
    # Arrange
    cards = next(s for s in GUI_SURFACES if s.package == "scitex-cards")
    # Act
    target = cards.target_port
    # Assert
    assert 31290 <= target <= 31299


def test_live_paper_target_port_in_3129x_block():
    # Arrange
    live_paper = next(s for s in GUI_SURFACES if s.package == "scitex-live-paper")
    # Act
    target = live_paper.target_port
    # Assert
    assert 31290 <= target <= 31299
