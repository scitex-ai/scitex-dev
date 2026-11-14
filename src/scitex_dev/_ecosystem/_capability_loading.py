"""Explicit trusted capability-factory loading with import-metadata checks.

Discovery stays inert. This is not a sandbox, publisher attestation or proof of
executed bytecode. Normal package initialization runs only on an explicit call;
the caller must bound trusted provider execution. No capability operation runs.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from collections.abc import Sequence
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

from .._core.provider_metadata import ProviderMetadata
from ._capability_contract import parse_capability_declaration
from ._capability_inventory import Capability
from ._capability_parent_records import resolve_capability_provider_chain


def _check_spec(spec, name, expected):
    if spec is None or spec.name != name or type(spec.loader) is not SourceFileLoader:
        raise ValueError(f"unqualified provider import specification: {name}")
    if spec.origin is None or Path(spec.origin).resolve() != expected:
        raise ValueError(f"provider import origin differs from RECORD: {name}")
    if Path(spec.loader.get_filename(name)).resolve() != expected:
        raise ValueError(f"provider loader filename differs from RECORD: {name}")
    locations = spec.submodule_search_locations
    if expected.name == "__init__.py":
        if locations is None or tuple(Path(item).resolve() for item in locations) != (expected.parent,):
            raise ValueError(f"provider package search path differs from RECORD: {name}")
    elif locations is not None:
        raise ValueError(f"provider module unexpectedly declares a package path: {name}")


def _check_module(module, name, expected):
    if type(module) is not ModuleType or module.__name__ != name:
        raise ValueError(f"unqualified provider module object: {name}")
    _check_spec(module.__spec__, name, expected)
    if Path(module.__file__).resolve() != expected or module.__loader__ is not module.__spec__.loader:
        raise ValueError(f"provider module file differs from RECORD: {name}")
    package = name if expected.name == "__init__.py" else name.rpartition(".")[0]
    if module.__package__ != package:
        raise ValueError(f"provider package context differs from RECORD: {name}")
    if expected.name == "__init__.py" and tuple(Path(item).resolve() for item in module.__path__) != (expected.parent,):
        raise ValueError(f"provider package search path differs from RECORD: {name}")


def load_capability_declaration(
    provider: ProviderMetadata, *, path: Sequence[str | Path] | None = None,
) -> tuple[Capability, ...]:
    """Load one explicitly selected trusted factory and parse its plain data.

    Metadata path selects manifest discovery only; it never changes sys.path.
    Standard imports may execute package initialization and dependencies.
    Require regular source-loader metadata matching every recorded parent and
    target before invoking one synchronous, zero-argument function defined in the
    selected module. Re-exported factories and callable objects are unsupported. Reject
    changed file records and malformed results; no behavioral acceptance follows.
    Import metadata is mutable and filesystem observations are not transactional.
    """
    files = resolve_capability_provider_chain(provider, path=path)
    target, _, attribute = provider.target.partition(":")
    parts = target.split(".")
    loaded = []
    for length, expected in enumerate(files, 1):
        name = ".".join(parts[:length])
        _check_spec(importlib.util.find_spec(name), name, expected)
        try:
            module = importlib.import_module(name)
        except Exception as exc:
            raise ValueError(f"capability provider import failed: {name}") from exc
        _check_module(module, name, expected)
        loaded.append((module, name, expected))
    if resolve_capability_provider_chain(provider, path=path) != files:
        raise ValueError("provider file chain changed during import")
    factory = loaded[-1][0]
    try:
        for component in attribute.split("."):
            factory = getattr(factory, component)
    except AttributeError as exc:
        raise ValueError("capability factory attribute is missing") from exc
    if not callable(factory):
        raise ValueError("capability factory must be callable")
    if (not inspect.isfunction(factory) or factory.__module__ != target
            or Path(factory.__code__.co_filename).resolve() != files[-1]):
        raise ValueError("capability factory must be a function defined in the selected module")
    if inspect.iscoroutinefunction(factory) or inspect.isasyncgenfunction(factory):
        raise ValueError("capability factory must be synchronous")
    # Later initializers or attribute lookup can change an earlier parent.
    # Check the entire loaded chain immediately before the only factory call.
    if resolve_capability_provider_chain(provider, path=path) != files:
        raise ValueError("provider file chain changed before factory execution")
    for module, name, expected in loaded:
        _check_module(module, name, expected)
    try:
        payload = factory()
    except Exception as exc:
        raise ValueError("capability factory failed") from exc
    if inspect.isawaitable(payload):
        if inspect.iscoroutine(payload):
            payload.close()
        raise ValueError("capability factory returned an awaitable")
    if resolve_capability_provider_chain(provider, path=path) != files:
        raise ValueError("provider file chain changed during factory execution")
    for module, name, expected in loaded:
        _check_module(module, name, expected)
    return parse_capability_declaration(payload, provider=provider)
