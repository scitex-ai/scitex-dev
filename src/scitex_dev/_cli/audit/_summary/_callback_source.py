"""Read already-loaded CLI bindings without importing or invoking providers."""

import sys
from types import FunctionType, ModuleType

import click


def loaded_bootstrap_module(entry_point):
    """Find a published Python-function console bootstrap, without calling it."""
    try:
        module = sys.modules.get(entry_point.module)
        if type(module) is not ModuleType:
            return None
        value = module
        for part in (entry_point.attr or "").split("."):
            value = vars(value).get(part)
        namespace = entry_point.module.split(".")[0]
        if type(value) is FunctionType and type(value.__module__) is str and (
            value.__module__ == namespace
            or value.__module__.startswith(namespace + ".")
        ):
            return module
    except (AttributeError, TypeError, ValueError):
        pass
    return None


def bound_callback_module(command):
    """Require a loaded ordinary module that publishes this Click callback."""
    callback = vars(command).get("callback")
    if type(callback) is not FunctionType or type(callback.__module__) is not str:
        return None
    name = callback.__module__
    module = sys.modules.get(name)
    if type(module) is not ModuleType:
        return None
    published = any(
        isinstance(value, click.Command) and vars(value).get("callback") is callback
        for value in tuple(vars(module).values())
    )
    return (name, module) if published else None
