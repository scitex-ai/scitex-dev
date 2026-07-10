#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem per-target audit commands: `audit-cli`, `audit-mcp-tools`,
`audit-python-apis`, `audit-skills`, `audit-project`, `audit-django`,
`init-config`.

Split from the former flat `_audit_per_target.py` module (2026-07-10,
CLI-standardization audit pass) — one command per file, mirroring the
convention already used elsewhere under `_cmds/`. This `__init__.py`
is the thin orchestrator; `ecosystem/_registry.py`'s
``from ._cmds import (..., _audit_per_target, ...)`` +
``_audit_per_target.register(ecosystem)`` call site is unchanged since
a package's ``__init__.py`` satisfies the same import shape as the
former module.
"""

from ._cli_cmd import register as _register_cli
from ._django_cmd import register as _register_django
from ._init_config_cmd import register as _register_init_config
from ._mcp_tools_cmd import register as _register_mcp_tools
from ._project_cmd import register as _register_project
from ._python_apis_cmd import register as _register_python_apis
from ._skills_cmd import register as _register_skills


def register(ecosystem):
    _register_cli(ecosystem)
    _register_mcp_tools(ecosystem)
    _register_python_apis(ecosystem)
    _register_skills(ecosystem)
    _register_project(ecosystem)
    _register_django(ecosystem)
    _register_init_config(ecosystem)


__all__ = ["register"]
