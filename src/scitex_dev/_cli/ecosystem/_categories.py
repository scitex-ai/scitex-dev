#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Category layout for `scitex-dev ecosystem --help`.

Section ordering for the categorised --help. Names below MUST match the
registered subcommand names; anything not listed falls into the built-in
"Other" section so nothing silently disappears.
"""

from __future__ import annotations

ECOSYSTEM_COMMAND_CATEGORIES = [
    (
        "Audit",
        [
            "audit-all",
            "audit-brand",
            "audit-cli",
            "audit-django",
            "audit-mcp-tools",
            "audit-project",
            "audit-registry-layout",
            "audit-python-apis",
            "audit-skills",
            "audit-summary",
            "list-audit-rules",
        ],
    ),
    (
        "Bulk",
        [
            "bulk",
        ],
    ),
    (
        "Discovery",
        [
            "list",
            "gui",
            "show-graph",
            "show-stats",
            # `dashboard` / `start-dashboard` moved to the top-level
            # canonical `gui` group (§12); what remains here are hidden
            # Phase W aliases, which the categorised help never lists.
        ],
    ),
    (
        "Quality",
        [
            "validate-versions",
            "install-audit-gate",
        ],
    ),
    (
        "Maintenance",
        [
            "clean-root",
            "init-config",
            "clone",
            "validate-sync",
            "prune-merged",
            # The daily two-dimensional sweep: every package on every
            # host, checkouts to develop plus local and remote branch
            # collection. Dry-run by default; `prune-branches` remains
            # the conservative, config-gated, local-only collector.
            "branch-hygiene",
            "ci-template",
            # Declared HOST state (journald persistence, sysctl drop-ins
            # ...) federated from every leaf's `scitex_dev.host_config`
            # provider. `check` is unprivileged; `apply` needs root.
            "host-config",
        ],
    ),
    (
        "Scheduled jobs",
        [
            "cron",
            "systemd",
            "daemon",
            # `up` provisions the supervisor unit + crontab block;
            # `run` is the supervisor itself (systemd ExecStart);
            # `status` reads the supervisor's state snapshot.
            "up",
            "run",
            "status",
        ],
    ),
    (
        "Legacy (use `bulk` instead)",
        [
            "install",
            "sync",
            "pull",
            "checkout",
            "test-remote",
            "sync-remote",
        ],
    ),
]


__all__ = ["ECOSYSTEM_COMMAND_CATEGORIES"]
