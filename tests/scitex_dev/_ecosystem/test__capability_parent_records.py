"""Resolve real installed record chains without executing package initializers."""

import base64
import hashlib

import pytest

from scitex_dev._ecosystem._capability_providers import read_capability_providers
from scitex_dev._ecosystem._capability_parent_records import resolve_capability_provider_chain
from scitex_dev._ecosystem._capability_resolution import resolve_capability_provider_module


def installed(root, module="chain_owned.nested.provider", package=False):
    info = root / "chain_owner-1.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: chain-owner\nVersion: 1.0\n")
    (info / "entry_points.txt").write_text(
        f"[scitex_dev.capabilities]\ndefault = {module}:inventory\n"
    )
    parts = module.split(".")
    files = [root.joinpath(*parts[:i], "__init__.py") for i in range(1, len(parts))]
    target = root.joinpath(*parts, "__init__.py") if package else root.joinpath(*parts).with_suffix(".py")
    files.append(target)
    rows = []
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = b"raise RuntimeError('chain resolution must never execute this file')\n"
        path.write_bytes(data)
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        rows.append(f"{path.relative_to(root).as_posix()},sha256={digest},{len(data)}\n")
    (info / "RECORD").write_text("".join(rows))
    return read_capability_providers(path=[root])[0], info, files


@pytest.mark.parametrize("module", ["chain_owned", "chain_owned.provider", "chain_owned.nested.provider"])
@pytest.mark.parametrize("package", [False, True])
def test_regular_parent_chain_and_target_are_returned_without_execution(tmp_path, module, package):
    # Arrange
    provider, _, files = installed(tmp_path, module=module, package=package)
    # Act
    chain = resolve_capability_provider_chain(provider, path=[tmp_path])
    # Assert
    assert chain == tuple(path.resolve() for path in files)


def damaged_parent(root, index, damage):
    provider, info, files = installed(root)
    parent = files[index]
    rows = (info / "RECORD").read_text().splitlines(keepends=True)
    if damage == "unlisted":
        rows.pop(index)
    elif damage == "missing":
        parent.unlink()
    elif damage == "changed":
        parent.write_text("changed = True\n")
    elif damage == "unsigned":
        name, _, size = rows[index].split(",")
        rows[index] = f"{name},,{size}"
    elif damage == "duplicate":
        rows.append(rows[index])
    else:
        replacement = root / "replacement.py"
        replacement.write_bytes(parent.read_bytes())
        parent.unlink()
        parent.symlink_to(replacement)
    (info / "RECORD").write_text("".join(rows))
    return provider


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("damage,reason", [
    ("unlisted", "uniquely listed"), ("missing", "file is missing"),
    ("changed", "digest mismatch"), ("unsigned", "digest is missing"),
    ("duplicate", "uniquely listed"), ("redirected", "redirected"),
])
def test_each_parent_must_have_unique_unchanged_owned_bytes(tmp_path, index, damage, reason):
    # Arrange
    provider = damaged_parent(tmp_path, index, damage)
    # Act
    def resolve():
        return resolve_capability_provider_chain(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match=f"parent package.*{reason}"):
        resolve()


def test_other_distribution_cannot_supply_a_missing_parent_claim(tmp_path):
    # Arrange
    provider, info, _ = installed(tmp_path)
    rows = (info / "RECORD").read_text().splitlines(keepends=True)
    (info / "RECORD").write_text("".join(rows[1:]))
    other = tmp_path / "other_owner-1.0.dist-info"
    other.mkdir()
    (other / "METADATA").write_text("Metadata-Version: 2.1\nName: other-owner\nVersion: 1.0\n")
    (other / "RECORD").write_text(rows[0])
    # Act
    def resolve():
        return resolve_capability_provider_chain(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="parent package.*uniquely listed"):
        resolve()


def test_namespace_parent_has_no_regular_package_qualification(tmp_path):
    # Arrange
    provider, info, files = installed(tmp_path)
    files[0].unlink()
    rows = (info / "RECORD").read_text().splitlines(keepends=True)
    (info / "RECORD").write_text("".join(rows[1:]))
    # Act
    def resolve():
        return resolve_capability_provider_chain(provider, path=[tmp_path])
    # Assert
    with pytest.raises(ValueError, match="parent package.*uniquely listed"):
        resolve()


def test_target_only_resolver_does_not_claim_parent_qualification(tmp_path):
    # Arrange
    provider, info, files = installed(tmp_path)
    rows = (info / "RECORD").read_text().splitlines(keepends=True)
    (info / "RECORD").write_text(rows[-1])
    # Act
    target = resolve_capability_provider_module(provider, path=[tmp_path])
    # Assert
    assert target == files[-1].resolve()


def test_install_root_alias_preserves_the_regular_chain(tmp_path):
    # Arrange
    real = tmp_path / "real"
    provider, _, files = installed(real)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    # Act
    chain = resolve_capability_provider_chain(provider, path=[alias])
    # Assert
    assert chain == tuple(path.resolve() for path in files)
