#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/hooks/__init__.py
"""Federated AGENT GUARDRAIL declaration for the SciTeX ecosystem.

Every scitex leaf declares the hook rules it owns by registering a callable
under the ``scitex_dev.hooks`` entry-point group; :func:`discover_hooks`
aggregates them, deduplicated by rule id. This is the same federation used by
``scitex_dev.jobs``, ``scitex_dev.system_deps``, ``scitex_dev.gate`` and
``scitex_dev.host_config`` -- and scitex-dev participates in it as a LEAF,
not as a privileged parent.

NOT TO BE CONFUSED WITH ``scitex_dev._hooks``, which is the private git-hook
runner (pre-push, lint, testmon) for scitex-dev's own repository.

Example provider (in a leaf package)::

    # scitex_agent_container/_hook_rules.py
    from scitex_dev.hooks import HookRule

    _PROVIDER = "scitex-agent-container"

    def provide() -> list[HookRule]:
        return [
            HookRule(
                id="sac.no-raw-apptainer-build",
                rule="Build sac images through `sac image build`, never a raw "
                     "`apptainer build`.",
                reason="A raw build produces a SIF with no provenance that "
                       "does not match the managed pipeline's output.",
                event="pre-tool-use",
                severity="deny",
                matches=("Bash",),
                script="hooks/deny_raw_apptainer_build.sh",
                provider=_PROVIDER,
            ),
        ]

    # pyproject.toml
    # [project.entry-points."scitex_dev.hooks"]
    # scitex-agent-container = "scitex_agent_container._hook_rules:provide"
"""

from ._discover import ENTRY_POINT_GROUP, discover_hooks, rules_of_provider
from ._spec import (
    ALLOWED_EVENTS,
    ALLOWED_SEVERITIES,
    HookRule,
    HookRuleProvider,
    resolve_asset,
)

__all__ = [
    "ALLOWED_EVENTS",
    "ALLOWED_SEVERITIES",
    "HookRule",
    "HookRuleProvider",
    "resolve_asset",
    "ENTRY_POINT_GROUP",
    "discover_hooks",
    "rules_of_provider",
]
