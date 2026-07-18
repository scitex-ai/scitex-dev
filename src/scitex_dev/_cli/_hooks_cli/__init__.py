"""``scitex-dev hooks`` — install / update / list / path the canonical agent hooks.

The 2026-06-12 ripple-wm dogfood pinned the fanned-out-copy class:
~10 deployed copies of ``run_lint.sh`` across operator projects each
drift independently. Pillar 0 (#169) shipped the canonical hook inside
scitex-dev at ``scitex_dev/_hooks/run_lint.sh`` so the authoritative
source travels with the pip-installed package. This CLI is the **durable
kill** for the fan-out class: install the canonical hook into a target
project as a SYMLINK so future scitex-dev releases automatically
propagate without operator action.

Subcommands
-----------
``scitex-dev hooks install --target <project>``
    Symlink the bundled hooks into the standard deploy tree. With
    ``--force`` overwrites an existing target; without ``--force``
    refuses if a non-symlink file is already present.
``scitex-dev hooks update --target <project>``
    Re-link the project's hooks to the currently-installed scitex-dev's
    bundled scripts (``install --force`` for an existing tree).
``scitex-dev hooks list --target <project>``
    Report install status per hook: ok / drift / stale / missing.
``scitex-dev hooks show-path <name>``
    Print the absolute filesystem path of the bundled hook ``<name>``.
``scitex-dev hooks enable-pre-push --target <project>``
    Install the canonical ``pre-push`` gate (audit-all + diff-scoped
    ruff/import-smoke/testmon) AND wire ``git config core.hooksPath
    .githooks`` in one step, so it fires on every ``git push``. Failures
    block the push with a clear message naming WHAT failed and HOW to
    bypass (``--no-verify`` is NOT disabled — safe-by-default, not
    no-escape). Distributable via the same symlink mechanism as
    ``run_lint``, so future releases auto-propagate.

Module map
----------
- :mod:`_registry`  — ``KNOWN_HOOKS`` + symlink-status helpers
- :mod:`_install`   — ``install`` and ``update`` leaves
- :mod:`_inspect`   — ``list`` and ``show-path`` leaves (+ alias)
- :mod:`_pre_push`  — ``enable-pre-push`` (symlink + ``core.hooksPath``)
"""

from __future__ import annotations

from ..._ecosystem.help_spec import CliHelp, Example, SpecGroup
from ._inspect import register_inspect
from ._install import register_install
from ._pre_push import register_pre_push
from ._registry import KNOWN_HOOKS


def register_hooks_commands(main) -> None:
    """Attach the ``hooks`` subgroup to the top-level ``scitex-dev`` click group.

    Called from ``scitex_dev._cli._integrations`` alongside the other
    ``register_*_commands(main)`` registrations.
    """

    @main.group(
        "hooks",
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Manage scitex-dev's bundled PostToolUse agent-feedback hooks.",
            description=(
                "Pillar 0 follow-up (#169) — replaces the per-project "
                "fanned-out run_lint.sh copies with a symlink to the "
                "canonical version shipped inside the pip-installed "
                "scitex-dev package. Future scitex-dev releases "
                "auto-propagate without operator action. Adds "
                "`enable-pre-push`: the local audit + scope-test gate that "
                "fires before every `git push`.",
            ),
            examples=(
                Example(
                    "{prog} hooks install --target ~/proj/my-research",
                    "Install the canonical hooks.",
                ),
                Example(
                    "{prog} hooks enable-pre-push --target ~/proj/my-research",
                    "Install + wire the pre-push gate.",
                ),
            ),
        ),
    )
    def hooks_group():  # pragma: no cover - click group body is empty by design
        pass

    register_install(hooks_group)
    register_inspect(hooks_group)
    register_pre_push(hooks_group)


__all__ = ["KNOWN_HOOKS", "register_hooks_commands"]
