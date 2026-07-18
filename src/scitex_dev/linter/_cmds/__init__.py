"""Click command modules for ``scitex-dev linter``.

Each module exposes ``register(main_group)``, which attaches its
command(s) to the root group and returns them. Split out of ``cli.py``
(512-line budget) when the free-form help strings were converted to the
spec'd :class:`~scitex_dev._ecosystem.help_spec.CliHelp` constructor.

The flat ``_cmd_format.py`` / ``_cmd_rules.py`` names one level up
belong to the LEGACY argparse handlers, which is why the Click surface
lives in this package instead.
"""

# EOF
