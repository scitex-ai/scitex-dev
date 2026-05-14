#!/usr/bin/env python3
"""Tests for scitex_dev.side_effects — SideEffect dataclass."""

import pytest

from scitex_dev._core.side_effects import SideEffect


class TestSideEffect:
    def test_creation_defaults_undoable_to_false_se_type_file_create(self):
        # Arrange
        # Act
        # Assert
        se = SideEffect(type="file_create", target="/tmp/out.csv")
        assert se.type == "file_create"


    def test_creation_defaults_undoable_to_false_se_target_tmp_out_csv(self):
        # Arrange
        # Act
        # Assert
        se = SideEffect(type="file_create", target="/tmp/out.csv")
        assert se.target == "/tmp/out.csv"


    def test_creation_defaults_undoable_to_false_se_undoable_is_false(self):
        # Arrange
        # Act
        # Assert
        se = SideEffect(type="file_create", target="/tmp/out.csv")
        assert se.undoable is False

    def test_undoable_flag_is_stored(self):
        # Arrange
        # Act
        # Assert
        se = SideEffect(type="file_modify", target="/tmp/f.py", undoable=True)
        assert se.undoable is True

    def test_str_format_is_type_colon_target(self):
        # Arrange
        # Act
        # Assert
        se = SideEffect(type="network", target="api.example.com")
        assert str(se) == "network: api.example.com"

    def test_frozen_dataclass_rejects_attribute_assignment(self):
        # Arrange
        # Act
        # Assert
        se = SideEffect(type="cache_write", target="/tmp/cache")
        with pytest.raises(AttributeError):
            se.target = "other"

    def test_hashable_when_fields_match_hash_se1_hash_se2(self):
        # Arrange
        # Act
        # Assert
        se1 = SideEffect(type="file_create", target="/a")
        se2 = SideEffect(type="file_create", target="/a")
        assert hash(se1) == hash(se2)


    def test_hashable_when_fields_match_se1_se2(self):
        # Arrange
        # Act
        # Assert
        se1 = SideEffect(type="file_create", target="/a")
        se2 = SideEffect(type="file_create", target="/a")
        assert se1 == se2
