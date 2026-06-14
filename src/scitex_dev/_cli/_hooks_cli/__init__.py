"""``scitex-dev hooks`` — install / update / list / path the canonical agent hooks.

The 2026-06-12 ripple-wm dogfood pinned the fanned-out-copy class:
~10 deployed copies of ``run_lint.sh`` across operator projects each
drift independently. Pillar 0 (#169) shipped the canonical hook
inside scitex-dev at ``scitex_dev/_hooks/run_lint.sh`` so the
authoritative source travels with the pip-installed package. This
CLI is the **durable kill** for the fan-out class: install the
canonical hook into a target project as a SYMLINK so future scitex-
dev releases automatically propagate without operator action.

Subcommands
-----------
``scitex-dev hooks install --target <project>``
    Create the standard hook tree at ``<project>/docs/to_claude/
    hooks/post-tool-use/`` and symlink the bundled ``run_lint.sh``
    into it. With ``--force`` overwrites an existing target; without
    ``--force`` refuses if a non-symlink file is already present.

``scitex-dev hooks update --target <project>``
    Re-link the project's ``run_lint.sh`` to the currently-installed
    scitex-dev's bundled script. Equivalent to ``install --force`` for
    a project that already has the directory tree.

``scitex-dev hooks list --target <project>``
    Report what's installed: each known hook + whether it points to
    the bundled canonical (ok), drift, stale, or missing.

``scitex-dev hooks print-path <name>``
    Print the absolute filesystem path of the bundled hook ``<name>``.
    Useful for shell scripts that want to manage their own symlinks.

``scitex-dev hooks enable-pre-push --target <project>``
    Install the canonical ``pre-push`` gate AND wire
    ``git config core.hooksPath .githooks`` in one step. The gate
    runs ``scitex-dev ecosystem audit-all`` + scope-bound pytest
    (``--testmon -m "not slow and not integration"``) before
    ``git push`` proceeds. Failures block the push with a clear
    message naming WHAT failed and HOW to bypass (``--no-verify`` is
    NOT disabled — the gate is "safe-by-default", not "no-escape").
    Distributable: same symlink mechanism as ``run_lint``, so future
    scitex-dev releases auto-propagate to every project that ran
    ``enable-pre-push`` once.

Hooks the CLI knows about
-------------------------
``run_lint`` → bundled at ``scitex_dev._hooks.run_lint_sh_path()``.
    The PostToolUse SciTeX-pattern-check hook from Pillar 0.
``pre_push`` → bundled at ``scitex_dev._hooks.pre_push_sh_path()``.
    The local pre-push gate (audit-all + scope tests). Installed
    via ``hooks install --name pre_push`` (raw) or
    ``hooks enable-pre-push`` (also wires ``core.hooksPath``).

Future canonical hooks register themselves by adding an entry to
:data:`KNOWN_HOOKS` (in ``_registry``).

Module map
----------
- :mod:`_registry`  — ``KNOWN_HOOKS`` + internal status helpers
- :mod:`_install`   — ``install`` and ``update`` subcommands
- :mod:`_inspect`   — ``list`` and ``print-path`` subcommands
- :mod:`_pre_push`  — ``enable-pre-push`` (symlink + ``core.hooksPath``)
- :mod:`_register`  — top-level ``register_hooks_commands(main)`` wiring
"""

from __future__ import annotations

from ._register import register_hooks_commands
from ._registry import KNOWN_HOOKS

__all__ = ["KNOWN_HOOKS", "register_hooks_commands"]
