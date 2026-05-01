#!/usr/bin/env python3
"""Tests for scitex_dev.side_effects — SideEffect dataclass."""

import pytest

from scitex_dev.side_effects import SideEffect


class TestSideEffect:
    def test_creation(self):
        se = SideEffect(type="file_create", target="/tmp/out.csv")
        assert se.type == "file_create"
        assert se.target == "/tmp/out.csv"
        assert se.undoable is False

    def test_undoable(self):
        se = SideEffect(type="file_modify", target="/tmp/f.py", undoable=True)
        assert se.undoable is True

    def test_str_format(self):
        se = SideEffect(type="network", target="api.example.com")
        assert str(se) == "network: api.example.com"

    def test_frozen(self):
        se = SideEffect(type="cache_write", target="/tmp/cache")
        with pytest.raises(AttributeError):
            se.target = "other"

    def test_hashable(self):
        se1 = SideEffect(type="file_create", target="/a")
        se2 = SideEffect(type="file_create", target="/a")
        assert hash(se1) == hash(se2)
        assert se1 == se2
