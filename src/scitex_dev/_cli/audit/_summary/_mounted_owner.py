"""Identify already-loaded mounted Click owners without importing peers.

A wheel may ship its authoritative CLI dictionary as
``<top_level_import>/_cli_audit_dict.yaml``. Only the distribution owning
the loaded console entry point may provide that resource. RECORD
membership, source identity, containment, size and digest are checked;
an absent or invalid resource never falls back to the mounting project.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.metadata as im
import sys
from dataclasses import dataclass
from pathlib import Path

import click

RESOURCE_NAME = "_cli_audit_dict.yaml"


@dataclass(frozen=True)
class MountedOwner:
    """Exact distribution identity and its verified dictionary resource."""

    identity: tuple[str, str, str]
    distribution: str
    resource: Path | None
    reason: str
    ambiguous: bool = False
    payload: bytes | None = None

    def provenance(self, full: str) -> str:
        resource = str(self.resource) if self.resource else self.reason
        return (
            f"{full}: cli-audit owner {self.distribution}; "
            f"dictionary {resource} (via installed RECORD)"
        )


def _loaded_command(ep):
    """Resolve only existing module dictionaries; never call ep.load()."""
    try:
        module = sys.modules.get(ep.module)
        value = module
        for part in (ep.attr or "").split("."):
            value = vars(value).get(part)
        callback = vars(value).get("callback")
        namespace = ep.module.split(".")[0]
        callback_module = getattr(callback, "__module__", "")
        if not isinstance(value, click.Command) or not (
            callback_module.startswith(namespace + ".") or callback_module == namespace
        ):
            return None
        return module, callback
    except (AttributeError, TypeError, ValueError):
        return None


def _recorded_owner(ep, module, dist) -> MountedOwner:
    """Validate the entry-point source and exact packaged dictionary."""
    name = dist.metadata["Name"] or "<unnamed>"
    namespace = ep.module.split(".")[0]
    install_root = Path(dist.locate_file("")).resolve()
    package_root = Path(dist.locate_file(namespace)).resolve()
    identity = (name.lower().replace("_", "-"), str(install_root), namespace)
    resource_rel = f"{namespace}/{RESOURCE_NAME}"

    def rejected(reason):
        return MountedOwner(identity, name, None, f"{resource_rel}: {reason}")

    if not package_root.is_relative_to(install_root):
        return rejected("package escapes distribution root")
    if dist.read_text("RECORD") is None:
        return rejected("distribution has no RECORD")
    files = {str(member): member for member in dist.files or ()}
    source = vars(module).get("__file__")
    if not source:
        return rejected("entry-point module has no source path")
    source = Path(source).resolve()
    source_members = (
        ep.module.replace(".", "/") + ".py",
        ep.module.replace(".", "/") + "/__init__.py",
    )
    if not source.is_relative_to(package_root) or not any(
        member in files and Path(dist.locate_file(member)).resolve() == source
        for member in source_members
    ):
        return rejected("entry-point source is not owned by distribution RECORD")
    member = files.get(resource_rel)
    if member is None:
        return rejected("absent from distribution RECORD")
    resource = Path(dist.locate_file(member)).resolve()
    if not resource.is_relative_to(package_root):
        return rejected("resource escapes owning package")
    try:
        payload = resource.read_bytes()
    except OSError:
        return rejected("recorded resource is unreadable")
    digest = member.hash
    if member.size != len(payload) or digest is None or digest.mode != "sha256":
        return rejected("resource lacks matching RECORD size/sha256")
    actual = (
        base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
    )
    if actual != digest.value:
        return rejected("resource does not match RECORD sha256")
    return MountedOwner(identity, name, resource, "verified", payload=payload)


class MountedOwners:
    """Per-walk index: callback identity, exact owners, no global cache."""

    def __init__(self):
        self._entries: dict[int, list] = {}
        self._owners: dict[int, MountedOwner | None] = {}
        self.sources: list[str] = []
        self._reported: set[tuple[str, tuple[str, str, str]]] = set()
        # Keep the distribution alongside its own entry points. This also
        # supports Python 3.9, whose EntryPoint lacks the newer .dist API.
        for dist in im.distributions():
            for ep in dist.entry_points:
                if ep.group != "console_scripts":
                    continue
                loaded = _loaded_command(ep)
                if loaded is None:
                    continue
                module, callback = loaded
                self._entries.setdefault(id(callback), []).append((ep, module, dist))

    def owner(self, cmd: click.Command) -> MountedOwner | None:
        key = id(vars(cmd).get("callback"))
        if key in self._owners:
            return self._owners[key]
        owners = {}
        for ep, module, dist in self._entries.get(key, ()):
            owner = _recorded_owner(ep, module, dist)
            owners[owner.identity] = owner
        if len(owners) == 1:
            self._owners[key] = next(iter(owners.values()))
            return self._owners[key]
        if not owners:
            self._owners[key] = None
            return None
        names = ", ".join(sorted(owner.distribution for owner in owners.values()))
        self._owners[key] = MountedOwner(
            (names, "", ""), names, None, "ambiguous distribution ownership", True
        )
        return self._owners[key]

    def report(self, owner: MountedOwner, full: str) -> None:
        key = (full, owner.identity)
        if key not in self._reported:
            self._reported.add(key)
            self.sources.append(owner.provenance(full))
