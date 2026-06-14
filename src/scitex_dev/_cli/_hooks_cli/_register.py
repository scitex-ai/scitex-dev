"""Top-level ``register_hooks_commands(main)`` entry point.

Wires the ``hooks`` click group onto the top-level scitex-dev CLI and
attaches each leaf subcommand. Called from
:mod:`scitex_dev._cli._root` alongside the other
``register_*_commands(main)`` registrations.
"""

from __future__ import annotations

from . import _inspect, _install, _pre_push


def register_hooks_commands(main) -> None:
    """Attach the ``hooks`` subgroup to the top-level ``scitex-dev`` click group."""
    import click

    @main.group("hooks", short_help="Manage agent-feedback hook scripts.")
    def hooks_group():  # pragma: no cover - click group body is empty by design
        """Manage scitex-dev's bundled hook scripts.

        Pillar 0 follow-up (#169) — replaces the per-project fanned-out
        ``run_lint.sh`` copies with a symlink to the canonical version
        shipped inside the pip-installed scitex-dev package. Future
        scitex-dev releases auto-propagate without operator action.

        Adds (2026-06-15): ``enable-pre-push`` — installs the canonical
        local pre-push gate (audit-all + scope tests) AND wires
        ``core.hooksPath`` so it fires on every ``git push``.
        """

    del click  # the import was just to avoid a lint flag for the decorator

    _install.register(hooks_group)
    _inspect.register(hooks_group)
    _pre_push.register(hooks_group)


__all__ = ["register_hooks_commands"]
