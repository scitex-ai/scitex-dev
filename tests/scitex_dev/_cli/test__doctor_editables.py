"""Exercise real PEP 610 metadata without importing or repairing installed code."""

import json
from importlib.metadata import distributions

from scitex_dev._cli._doctor_editables import check_editable_installs


def _distribution(tmp_path, direct, name="owned-editable"):
    site = tmp_path / "site"
    info = site / (name.replace("-", "_") + "-1.0.dist-info")
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n"
    )
    if direct is not None:
        (info / "direct_url.json").write_text(json.dumps(direct))
    return list(distributions(path=[str(site)]))


def test_missing_editable_source_is_failure_with_location(tmp_path):
    # Arrange
    source = tmp_path / "deleted project"
    installed = _distribution(
        tmp_path, {"url": source.as_uri(), "dir_info": {"editable": True}}
    )
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert (
        len(rows),
        rows[0]["status"],
        "owned-editable" in rows[0]["check"],
        str(source) in rows[0]["detail"],
        not source.exists(),
    ) == (1, "fail", True, True, True)


def test_existing_source_is_directory_health_not_import_acceptance(tmp_path):
    # Arrange
    source = tmp_path / "source with spaces"
    source.mkdir()
    (source / "__init__.py").write_text("raise RuntimeError('must not import')\n")
    installed = _distribution(
        tmp_path, {"url": source.as_uri(), "dir_info": {"editable": True}}
    )
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert (
        rows[0]["status"],
        "directory exists" in rows[0]["detail"],
        str(source) in rows[0]["detail"],
    ) == ("ok", True, True)


def test_source_file_is_not_a_source_directory(tmp_path):
    # Arrange
    source = tmp_path / "source"
    source.write_text("not a directory")
    installed = _distribution(
        tmp_path, {"url": source.as_uri(), "dir_info": {"editable": True}}
    )
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert (rows[0]["status"], "not a directory" in rows[0]["detail"]) == ("fail", True)


def test_dangling_source_link_is_failure_without_repair(tmp_path):
    # Arrange
    source = tmp_path / "linked-source"
    source.symlink_to(tmp_path / "absent", target_is_directory=True)
    installed = _distribution(
        tmp_path, {"url": source.as_uri(), "dir_info": {"editable": True}}
    )
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert (rows[0]["status"], source.is_symlink()) == ("fail", True)


def test_ordinary_wheel_has_no_editable_result(tmp_path):
    # Arrange
    installed = _distribution(tmp_path, None)
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert rows == []


def test_noneditable_local_install_has_no_editable_result(tmp_path):
    # Arrange
    installed = _distribution(
        tmp_path, {"url": tmp_path.as_uri(), "dir_info": {"editable": False}}
    )
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert rows == []


def test_nonlocal_source_is_unknown_without_network_lookup(tmp_path):
    # Arrange
    installed = _distribution(
        tmp_path,
        {
            "url": "file://unresolvable.invalid/private/project",
            "dir_info": {"editable": True},
        },
    )
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert (rows[0]["status"], "unsupported source URL" in rows[0]["detail"]) == (
        "skip",
        True,
    )


def test_malformed_metadata_is_unknown_not_healthy(tmp_path):
    # Arrange
    installed = _distribution(tmp_path, {})
    info = next((tmp_path / "site").glob("*.dist-info"))
    (info / "direct_url.json").write_text("not JSON")
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert (rows[0]["status"], "metadata" in rows[0]["detail"]) == ("skip", True)


def test_symlink_to_existing_source_directory_is_healthy(tmp_path):
    # Arrange
    target = tmp_path / "target"
    target.mkdir()
    source = tmp_path / "alias"
    source.symlink_to(target, target_is_directory=True)
    installed = _distribution(
        tmp_path, {"url": source.as_uri(), "dir_info": {"editable": True}}
    )
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert rows[0]["status"] == "ok"


def test_percent_escaped_source_is_decoded_only_once(tmp_path):
    # Arrange
    source = tmp_path / "literal%20source"
    source.mkdir()
    installed = _distribution(
        tmp_path, {"url": source.as_uri(), "dir_info": {"editable": True}}
    )
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert (rows[0]["status"], str(source) in rows[0]["detail"]) == ("ok", True)


def test_localhost_file_url_is_a_local_directory(tmp_path):
    # Arrange
    installed = _distribution(
        tmp_path,
        {
            "url": tmp_path.as_uri().replace("file://", "file://localhost"),
            "dir_info": {"editable": True},
        },
    )
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert rows[0]["status"] == "ok"


def test_nonobject_metadata_is_unknown(tmp_path):
    # Arrange
    installed = _distribution(tmp_path, ["invalid metadata"])
    # Act
    rows = check_editable_installs(installed)
    # Assert
    assert rows[0]["status"] == "skip"
