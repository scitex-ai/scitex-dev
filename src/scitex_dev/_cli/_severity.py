"""Warning spelling compatibility at the CLI boundary, without policy changes."""

import click


class SeverityChoice(click.Choice):
    """Accept both spellings and return the auditor's existing warning value."""

    def __init__(self, warning="warning", *, case_sensitive=True):
        if warning not in ("warn", "warning"):
            raise ValueError("warning must be 'warn' or 'warning'")
        self.warning = warning
        super().__init__(
            ["error", "warning", "warn", "info"], case_sensitive=case_sensitive
        )

    def convert(self, value, param, ctx):
        selected = super().convert(value, param, ctx)
        return self.warning if selected in ("warn", "warning") else selected
