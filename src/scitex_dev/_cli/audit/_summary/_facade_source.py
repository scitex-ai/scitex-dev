"""Read a published facade class without importing or invoking its module."""

import sys
from types import ModuleType

import click


def published_facade_module(command):
    """Return a real loaded class binding, not a distribution ownership claim.

    Callers must separately qualify both the console source and the bound
    callback against the same distribution's RECORD. Shared Click classes
    alone confer no application ownership.
    """
    if not isinstance(command, click.Command):
        return None
    cls = type(command)
    if type(cls) is not type:
        return None
    name = vars(cls).get("__module__")
    if type(name) is not str:
        return None
    module = sys.modules.get(name)
    if type(module) is not ModuleType or vars(module).get(cls.__name__) is not cls:
        return None
    return name, module
