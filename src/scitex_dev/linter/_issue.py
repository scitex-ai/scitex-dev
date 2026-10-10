"""Lightweight issue value shared by the engine and provider SPI."""

from dataclasses import dataclass

from ._rules._base import Rule


@dataclass
class Issue:
    rule: Rule
    line: int
    col: int
    source_line: str = ""


# Keep the historical import identity for persisted/pickled Issue values.
# checker.py re-exports this same class after lightweight construction.
Issue.__module__ = "scitex_dev.linter.checker"
