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
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType

import click

from ._callback_source import bound_callback_module, loaded_bootstrap_module
from ._facade_source import published_facade_module

RESOURCE_NAME = "_cli_audit_dict.yaml"


@dataclass(frozen=True)
class MountedOwner:
    """Exact distribution identity and its verified dictionary resource."""

    identity: tuple[str, str, str, str, str]
    distribution: str
    resource: Path | None
    reason: str
    ambiguous: bool = False
    payload: bytes | None = None
    # Membership/path evidence only, not a source digest or behavior attestation.
    source_record_owned: bool = False
    unowned_source_claims: tuple[str, ...] = ()

    def provenance(self, full: str) -> str:
        resource = str(self.resource) if self.resource else self.reason
        return (
            f"{full}: cli-audit owner {self.distribution}; "
            f"dictionary {resource} (via installed RECORD)"
        )


def _metadata_origin(dist) -> Path | None:
    """Read PathDistribution's private on-disk origin, or refuse attribution.

    ``Distribution`` has no public metadata-origin API. Only an actual Path
    stored in the standard implementation's instance dictionary is supported;
    custom/zip origins are not inferred from names or callable path adapters.
    """
    try:
        origin = vars(dist).get("_path")
        if not isinstance(origin, Path):
            return None
        origin = origin.resolve(strict=True)
        return origin if origin.is_dir() else None
    except (OSError, RuntimeError, TypeError):
        return None


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
    return _recorded_module_owner(ep.module, module, dist)


def _recorded_module_owner(module_name, module, dist, source_kind="entry-point"):
    """Apply the same RECORD and containment checks to a loaded CLI module."""
    name = dist.metadata["Name"] or "<unnamed>"
    version = dist.metadata["Version"] or ""
    namespace = module_name.split(".")[0]
    install_root = Path(dist.locate_file("")).resolve()
    package_root = Path(dist.locate_file(namespace)).resolve()
    origin = _metadata_origin(dist)
    # Unknown origins never grant a dictionary or collapse distinct objects.
    origin_key = str(origin) if origin is not None else f"unavailable:{id(dist)}"
    identity = (
        name.lower().replace("_", "-"),
        str(install_root),
        namespace,
        version,
        origin_key,
    )
    resource_rel = f"{namespace}/{RESOURCE_NAME}"
    source_record_owned = False

    def rejected(reason):
        return MountedOwner(
            identity,
            name,
            None,
            f"{resource_rel}: {reason}",
            source_record_owned=source_record_owned,
        )

    if origin is None:
        return rejected("distribution metadata origin unavailable")
    if not package_root.is_relative_to(install_root):
        return rejected("package escapes distribution root")
    if dist.read_text("RECORD") is None:
        return rejected("distribution has no RECORD")
    files = {str(member): member for member in dist.files or ()}
    source = vars(module).get("__file__")
    if not source:
        return rejected(f"{source_kind} module has no source path")
    source = Path(source).resolve()
    source_members = (
        module_name.replace(".", "/") + ".py",
        module_name.replace(".", "/") + "/__init__.py",
    )
    if not source.is_relative_to(package_root) or not any(
        member in files and Path(dist.locate_file(member)).resolve() == source
        for member in source_members
    ):
        return rejected(f"{source_kind} source is not owned by distribution RECORD")
    source_record_owned = True
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
    return MountedOwner(
        identity,
        name,
        resource,
        "verified",
        payload=payload,
        source_record_owned=True,
    )


class MountedOwners:
    """Per-walk index: callback identity, exact owners, no global cache."""

    def __init__(self):
        self._entries: dict[int, list] = {}
        self._bootstraps: dict[str, list] = {}
        self._facade_sources: dict[str, list] = {}
        self._facade_bindings: dict[str, list] = {}
        self._owners: dict[tuple[int, int], MountedOwner | None] = {}
        self._lexicons: dict[tuple, MountedOwner] = {}
        self.sources: list[str] = []
        self._reported: set[tuple[str, tuple[str, str, str, str, str]]] = set()
        self._source_dictionary = None
        # Keep the distribution alongside its own entry points. This also
        # supports Python 3.9, whose EntryPoint lacks the newer .dist API.
        for dist in im.distributions():
            for ep in dist.entry_points:
                if ep.group != "console_scripts":
                    continue
                module = sys.modules.get(ep.module)
                if type(module) is ModuleType:
                    self._facade_sources.setdefault(ep.module, []).append(
                        (ep, module, dist)
                    )
                loaded = _loaded_command(ep)
                if loaded is None:
                    module = loaded_bootstrap_module(ep)
                    if module is not None:
                        self._bootstraps.setdefault(ep.module.split(".")[0], []).append(
                            (ep, module, dist)
                        )
                    continue
                module, callback = loaded
                self._entries.setdefault(id(callback), []).append((ep, module, dist))

    def bind_audited_source(self, command, package, root, entry_point):
        """Admit only this audit's declared source subject, never a peer."""
        from ._source_dictionary import SourceDictionary

        self._source_dictionary = SourceDictionary.from_root(
            package, root, entry_point, command, self.owner(command)
        )

    def source_dictionary(self, command, owner):
        source = self._source_dictionary
        return source if source is not None and source.owns(command, owner) else None

    def owner(self, cmd: click.Command) -> MountedOwner | None:
        callback_key = id(vars(cmd).get("callback"))
        # A lazy facade and its delegate can share a callback while only the
        # facade class is published by the loaded console source.
        key = (callback_key, id(type(cmd)))
        if key in self._owners:
            return self._owners[key]
        claims = [
            _recorded_owner(ep, module, dist)
            for ep, module, dist in self._entries.get(callback_key, ())
        ]
        # Exact console claims keep precedence, including invalid ones. A
        # nested binding cannot rescue a rejected entry-point claim.
        if not claims:
            claims = self._callback_claims(cmd)
        if not claims:
            claims = self._facade_claims(cmd)
        recorded = {
            owner.identity: owner for owner in claims if owner.source_record_owned
        }
        rejected = tuple(
            f"{claim.distribution}: {claim.reason}"
            for claim in claims
            if not claim.source_record_owned
        )
        # No proven source retains a blocked context, never the parent dictionary.
        # Distinct entry points from one origin cannot overwrite proven ownership.
        owners = recorded or {owner.identity: owner for owner in claims}
        if len(owners) == 1:
            selected = next(iter(owners.values()))
            selected = replace(selected, unowned_source_claims=rejected)
            if selected.source_record_owned:
                # Freeze the first resource verdict/bytes for this metadata
                # origin. A nested lookup cannot swap in later file contents.
                original = self._lexicons.setdefault(selected.identity, selected)
                selected = replace(selected, resource=original.resource,
                                   payload=original.payload, reason=original.reason)
            self._owners[key] = selected
            return self._owners[key]
        if not owners:
            self._owners[key] = None
            return None
        names = ", ".join(sorted(owner.distribution for owner in owners.values()))
        reason = "ambiguous distribution ownership"
        if len({owner.distribution for owner in owners.values()}) < len(owners):
            origins = "; ".join(
                f"{identity[0]}=={identity[3]} at {identity[4]}"
                for identity in sorted(owners)
            )
            reason += f" (distinct metadata: {origins})"
        self._owners[key] = MountedOwner(
            (names, "", "", "", ""),
            names,
            None,
            reason,
            True,
            unowned_source_claims=rejected,
        )
        return self._owners[key]

    def _callback_claims(self, cmd):
        binding = bound_callback_module(cmd)
        if binding is None:
            return []
        name, module = binding
        namespace = name.split(".")[0]
        candidates = list(self._bootstraps.get(namespace, ()))
        candidates.extend(self._facade_bindings.get(namespace, ()))
        for entries in self._entries.values():
            candidates.extend(entry for entry in entries
                              if entry[0].module.split(".")[0] == namespace)
        claims = []
        for ep, console_module, dist in candidates:
            qualification = _recorded_owner(ep, console_module, dist)
            # Namespace spelling alone never establishes ownership. First
            # prove the loaded console source, then this callback's module.
            claims.append(
                _recorded_module_owner(name, module, dist, "bound callback")
                if qualification.source_record_owned else qualification
            )
        return claims

    def _facade_claims(self, cmd):
        facade = published_facade_module(cmd)
        if facade is None:
            return []
        binding = bound_callback_module(cmd)
        source_name, source_module = facade
        claims = []
        for ep, console_module, dist in self._facade_sources.get(source_name, ()):
            if console_module is not source_module:
                continue
            qualification = _recorded_owner(ep, console_module, dist)
            if qualification.source_record_owned:
                if binding is None:
                    qualification = replace(
                        qualification,
                        resource=None,
                        payload=None,
                        reason="facade callback binding unavailable",
                        source_record_owned=False,
                    )
                else:
                    callback_name, callback_module = binding
                    qualification = _recorded_module_owner(
                        callback_name, callback_module, dist, "bound callback"
                    )
                    if qualification.source_record_owned:
                        self._facade_bindings.setdefault(
                            callback_name.split(".")[0], []
                        ).append((ep, console_module, dist))
            claims.append(qualification)
        return claims

    def report(self, owner: MountedOwner, full: str) -> None:
        key = (full, owner.identity)
        if key not in self._reported:
            self._reported.add(key)
            self.sources.append(owner.provenance(full))
            self.sources.extend(
                f"{full}: unowned entry-point source claim {claim}"
                for claim in owner.unowned_source_claims
            )
