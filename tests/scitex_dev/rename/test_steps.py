"""Protected-only matches stay visible without broadening rename scope."""

import pytest

from scitex_dev import preview_rename
from scitex_dev.rename.config import RenameConfig
from scitex_dev.rename.steps import _literal_replace_content


@pytest.fixture(
    params=[
        ('prog_name="scitex-business"\n', "scitex-business"),
        ('StorePlugin(name="business_actuals")\n', "business_actuals"),
        ('db_table = "business_actuals"\n', "business_actuals"),
    ]
)
def protected_preview(tmp_path, request):
    body, pattern = request.param
    target = tmp_path / "cli.py"
    target.write_text(body)
    result = preview_rename(pattern, "replacement", directory=str(tmp_path))
    return result, target, body


@pytest.mark.parametrize(
    "key,expected",
    [
        ("content_files", 0),
        ("content_matches", 0),
        ("content_protected", 1),
        ("protected_files", 1),
    ],
)
def test_protected_only_summary(protected_preview, key, expected):
    # Arrange
    result, _, _ = protected_preview
    # Act
    actual = result.summary[key]
    # Assert
    assert actual == expected


def test_protected_only_preview_detail(protected_preview):
    # Arrange
    result, _, _ = protected_preview
    # Act
    actual = result.contents[0]["lines"][0]["action"]
    # Assert
    assert actual == "protect"


def test_protected_only_preview_preserves_bytes(protected_preview):
    # Arrange
    _, target, body = protected_preview
    # Act
    actual = target.read_text()
    # Assert
    assert actual == body


@pytest.fixture
def protected_application(tmp_path):
    target = tmp_path / "cli.py"
    body = 'prog_name="scitex-business"\n'
    target.write_text(body)
    before = target.stat()
    config = RenameConfig("scitex-business", "scitex-affairs", dry_run=False)
    result = _literal_replace_content(config, target, body, "c-000", False)
    return result, target, body, before


@pytest.mark.parametrize("key,expected", [("protected", 1), ("matches", 0)])
def test_protected_only_apply_report(protected_application, key, expected):
    # Arrange
    result, _, _, _ = protected_application
    # Act
    actual = result[key]
    # Assert
    assert actual == expected


def test_protected_only_apply_preserves_bytes(protected_application):
    # Arrange
    _, target, body, _ = protected_application
    # Act
    actual = target.read_text()
    # Assert
    assert actual == body


@pytest.mark.parametrize("field", ["st_mtime_ns", "st_ino"])
def test_protected_only_apply_does_not_rewrite(protected_application, field):
    # Arrange
    _, target, _, before = protected_application
    # Act
    actual = getattr(target.stat(), field)
    # Assert
    assert actual == getattr(before, field)


@pytest.mark.parametrize(
    "key,expected",
    [
        ("content_files", 1),
        ("content_matches", 1),
        ("content_protected", 1),
    ],
)
def test_plain_quoted_string_is_replaceable(tmp_path, key, expected):
    # Arrange
    (tmp_path / "cli.py").write_text('label = "business"\nprog_name="business"\n')
    # Act
    result = preview_rename("business", "affairs", directory=str(tmp_path))
    # Assert
    assert result.summary[key] == expected
