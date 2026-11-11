"""Bind a dictionary to the explicitly audited source, never to a peer."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from ._callback_source import bound_callback_module
from ._dict_root import DICT_RELPATH, resolved_dict_root


def _module_belongs(name: str, namespace: str, source: Path) -> bool:
    module = sys.modules.get(name)
    if type(module) is not ModuleType or not (
        name == namespace or name.startswith(namespace + ".")
    ):
        return False
    value = vars(module).get("__file__")
    if not isinstance(value, str):
        return False
    suffix = name.split(".")[1:]
    candidates = [source.joinpath(*suffix, "__init__.py")]
    if suffix:
        candidates.append(source.joinpath(*suffix[:-1], suffix[-1] + ".py"))
    actual = Path(value).resolve(strict=True)
    return actual.is_relative_to(source) and any(
        candidate.resolve() == actual for candidate in candidates
    )


def _normal_name(value: str) -> str:
    return value.lower().replace("_", "-")


@dataclass(frozen=True)
class SourceDictionary:
    """One source-subject identity and immutable dictionary bytes for a walk."""

    identity: tuple
    distribution: str
    root: Path
    namespace: str
    source: Path
    resource: Path
    payload: bytes

    @classmethod
    def from_root(cls, package, root, entry_point, command, owner):
        """Require matching declaration, loaded source and unambiguous owner."""
        if (
            root is None
            or owner is None
            or owner.ambiguous
            or owner.source_record_owned
        ):
            return None
        if _normal_name(owner.distribution) != _normal_name(package):
            return None
        if owner.identity[-1].startswith("unavailable:"):
            return None
        try:
            try:
                import tomllib
            except ImportError:  # Python 3.9/3.10; declared core dependency.
                import tomli as tomllib

            root = Path(root).resolve(strict=True)
            if resolved_dict_root()[0].resolve() != root:
                return None
            project_file = root / "pyproject.toml"
            if not project_file.resolve(strict=True).is_relative_to(root):
                return None
            project = tomllib.loads(project_file.read_text())["project"]
            if _normal_name(project["name"]) != _normal_name(package):
                return None
            if project.get("scripts", {}).get(package) != entry_point:
                return None
            module_name, _attribute = entry_point.split(":", 1)
            namespace = module_name.split(".")[0]
            if namespace != owner.identity[2]:
                return None
            module = sys.modules.get(namespace)
            if type(module) is not ModuleType:
                return None
            package_file = Path(vars(module)["__file__"]).resolve(strict=True)
            source = package_file.parent
            if package_file.name != "__init__.py" or not source.is_relative_to(root):
                return None
            binding = bound_callback_module(command)
            if binding is None or not _module_belongs(module_name, namespace, source):
                return None
            if not _module_belongs(binding[0], namespace, source):
                return None
            # Match the source project's explicit policy first; a checked-in
            # packaged dictionary is the owning source's default, not a peer.
            project_resource = root.joinpath(*DICT_RELPATH)
            resource = (
                project_resource
                if project_resource.exists() or project_resource.is_symlink()
                else source / "_cli_audit_dict.yaml"
            )
            resource = resource.resolve(strict=True)
            if not resource.is_relative_to(root) or not resource.is_file():
                return None
            fd = os.open(resource, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_size > 1024 * 1024:
                    return None
                with os.fdopen(os.dup(fd), "rb") as stream:
                    payload = stream.read(1024 * 1024 + 1)
                after, current = os.fstat(fd), resource.lstat()
                fields = (
                    "st_dev",
                    "st_ino",
                    "st_mode",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                )
                if (
                    len(payload) != before.st_size
                    or any(
                        getattr(before, field) != getattr(after, field)
                        or getattr(before, field) != getattr(current, field)
                        for field in fields
                    )
                    or resource.resolve(strict=True) != resource
                ):
                    return None
            finally:
                os.close(fd)
            payload.decode("utf-8")
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError):
            return None
        return cls(
            owner.identity,
            owner.distribution,
            root,
            namespace,
            source,
            resource,
            payload,
        )

    def owns(self, command, owner) -> bool:
        if owner is None or owner.ambiguous or owner.source_record_owned:
            return False
        if owner.identity != self.identity:
            return False
        binding = bound_callback_module(command)
        try:
            return binding is not None and _module_belongs(
                binding[0], self.namespace, self.source
            )
        except (OSError, RuntimeError, ValueError, TypeError):
            return False

    def provenance(self, full: str) -> str:
        digest = hashlib.sha256(self.payload).hexdigest()
        return (
            f"{full}: cli-audit source subject {self.distribution}; dictionary "
            f"{self.resource} (audited source {self.root}; sha256 {digest}; "
            "not an installed RECORD claim)"
        )
