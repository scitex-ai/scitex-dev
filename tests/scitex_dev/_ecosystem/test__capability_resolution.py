"""Actual distribution records qualify file facts without importing providers."""

import base64
import hashlib

import pytest

from scitex_dev._ecosystem._capability_providers import read_capability_providers
from scitex_dev._ecosystem._capability_resolution import resolve_capability_provider_module


def _installed(root, *, relative="owned_provider.py", digest=True, size=None):
    info = root / "owned_example-1.2.3.dist-info"
    info.mkdir(parents=True)
    info.joinpath("METADATA").write_text(
        "Metadata-Version: 2.1\nName: owned-example\nVersion: 1.2.3\n"
    )
    info.joinpath("entry_points.txt").write_text(
        "[scitex_dev.capabilities]\ndefault = owned_provider:inventory\n"
    )
    data = b"raise RuntimeError('metadata resolution must not import this')\n"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
    hash_field = "sha256=" + encoded if digest else ""
    record_size = len(data) if size is None else size
    info.joinpath("RECORD").write_text(f"{relative},{hash_field},{record_size}\n")
    return read_capability_providers(path=[root])[0], info, target


@pytest.mark.parametrize("relative", ["owned_provider.py", "owned_provider/__init__.py"])
def test_recorded_module_and_package_files_resolve_without_import(tmp_path, relative):
    # Arrange
    provider, _, target = _installed(tmp_path, relative=relative)
    # Act
    resolved = resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    assert resolved == target.resolve()


def test_missing_record_does_not_enable_a_source_fallback(tmp_path):
    # Arrange
    provider, info, _ = _installed(tmp_path)
    (info / "RECORD").unlink()
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="uniquely listed"):
        resolve()


def test_existing_unlisted_module_is_not_owned_by_declaration_alone(tmp_path):
    # Arrange
    provider, info, _ = _installed(tmp_path)
    (info / "RECORD").write_text("other.py,,\n")
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="uniquely listed"):
        resolve()


def test_recorded_missing_file_is_reported(tmp_path):
    # Arrange
    provider, _, target = _installed(tmp_path)
    target.unlink()
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="file is missing"):
        resolve()


def test_changed_module_bytes_do_not_match_the_record(tmp_path):
    # Arrange
    provider, _, target = _installed(tmp_path)
    target.write_text("changed = True\n")
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="digest mismatch"):
        resolve()


def test_absent_record_digest_is_not_a_verified_file(tmp_path):
    # Arrange
    provider, _, _ = _installed(tmp_path, digest=False)
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="digest is missing"):
        resolve()


def test_record_size_must_agree_with_verified_bytes(tmp_path):
    # Arrange
    provider, _, _ = _installed(tmp_path, size=1)
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="size mismatch"):
        resolve()


def test_module_symlink_redirection_is_refused(tmp_path):
    # Arrange
    provider, _, target = _installed(tmp_path)
    replacement = tmp_path / "other.py"
    replacement.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(replacement)
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="redirected"):
        resolve()


def test_multiple_module_shapes_are_ambiguous(tmp_path):
    # Arrange
    provider, info, target = _installed(tmp_path)
    package = tmp_path / "owned_provider" / "__init__.py"
    package.parent.mkdir()
    package.write_bytes(target.read_bytes())
    row = (info / "RECORD").read_text()
    (info / "RECORD").write_text(row + row.replace("owned_provider.py", "owned_provider/__init__.py"))
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="uniquely listed"):
        resolve()


def test_changed_declaration_cannot_reuse_an_earlier_snapshot(tmp_path):
    # Arrange
    provider, info, _ = _installed(tmp_path)
    (info / "entry_points.txt").write_text(
        "[scitex_dev.capabilities]\ndefault = another_provider:inventory\n"
    )
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="changed since discovery"):
        resolve()


def test_duplicate_distribution_identity_without_the_same_provider_is_ambiguous(tmp_path):
    # Arrange
    provider, _, _ = _installed(tmp_path)
    other = tmp_path / "duplicate-1.2.3.dist-info"
    other.mkdir()
    (other / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: owned-example\nVersion: 1.2.3\n"
    )
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="ownership is ambiguous"):
        resolve()


def test_non_metadata_provider_objects_are_rejected(tmp_path):
    # Arrange
    provider = {"distribution": "owned-example"}
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(TypeError, match="ProviderMetadata"):
        resolve()


def test_install_root_alias_is_distinct_from_a_module_redirection(tmp_path):
    # Arrange
    root = tmp_path / "real"
    provider, _, target = _installed(root)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    # Act
    resolved = resolve_capability_provider_module(provider, path=[alias])
    # Assert
    assert resolved == target.resolve()


@pytest.mark.parametrize("row", ["owned_provider.py,sha256=value\n",
                                  "owned_provider.py,sha256=value,1,extra\n"])
def test_malformed_record_rows_are_rejected(tmp_path, row):
    # Arrange
    provider, info, _ = _installed(tmp_path)
    (info / "RECORD").write_text(row)
    # Act
    def resolve():
        return resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="malformed row"):
        resolve()
