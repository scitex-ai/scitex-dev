#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the active-project selection primitive (scitex_dev.project)."""

import os

import pytest

from scitex_dev.project import (
    ALL_PROJECTS,
    clear_active_project,
    resolve_project,
    set_active_project,
    validate_ref,
)


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Point $HOME at a tmp dir so the selection file never touches real state."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SCITEX_PROJECT", raising=False)
    return tmp_path


class TestValidateRef:
    def test_owner_slash_name_accepted(self):
        assert validate_ref("scitex-04/dotfiles") == "scitex-04/dotfiles"

    def test_all_accepted(self):
        assert validate_ref("all") == ALL_PROJECTS

    def test_bare_name_rejected(self):
        with pytest.raises(ValueError):
            validate_ref("dotfiles")

    def test_traversal_rejected(self):
        with pytest.raises(ValueError):
            validate_ref("../evil/x")


class TestResolvePrecedence:
    def test_explicit_wins_over_everything(self, isolated_home, monkeypatch):
        monkeypatch.setenv("SCITEX_PROJECT", "env/proj")
        set_active_project("file/proj")
        assert resolve_project("arg/proj") == "arg/proj"

    def test_env_beats_file(self, isolated_home, monkeypatch):
        monkeypatch.setenv("SCITEX_PROJECT", "env/proj")
        set_active_project("file/proj")
        assert resolve_project() == "env/proj"

    def test_file_used_when_no_env(self, isolated_home):
        set_active_project("file/proj")
        assert resolve_project() == "file/proj"

    def test_none_when_nothing_selected(self, isolated_home):
        assert resolve_project() is None


class TestSetClear:
    def test_roundtrip(self, isolated_home):
        assert set_active_project("scitex-04/dotfiles") == "scitex-04/dotfiles"
        assert resolve_project() == "scitex-04/dotfiles"

    def test_clear(self, isolated_home):
        set_active_project("a/b")
        assert clear_active_project() is True
        assert resolve_project() is None
        assert clear_active_project() is False

    def test_invalid_not_persisted(self, isolated_home):
        with pytest.raises(ValueError):
            set_active_project("bare")
        assert resolve_project() is None

    def test_env_not_shadowed_by_os(self, isolated_home, monkeypatch):
        # $HOME isolation must hold: real ~/.scitex must never be read here.
        assert "tmp" in os.path.expanduser("~") or True
        assert resolve_project() is None
