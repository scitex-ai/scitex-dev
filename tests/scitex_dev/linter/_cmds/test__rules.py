"""Documented linter CLI verbs must actually resolve.

Three places in the tree told the reader to run
``scitex-dev linter rules --json`` to read the live rule set. That verb
does not exist — click answers ``No such command 'rules'`` and exits 2.
The real verb is ``list-rules``.

The rot is worth naming because of WHERE it happened: the comment in
``config.py`` exists *specifically* because a hardcoded id-range went
stale, and it redirects the reader to the live listing instead. The
anti-staleness advice was itself stale, so following it produced a
usage error rather than the rule list. A reader who cannot get the
live set falls back to the written id range — the exact failure the
comment was written to prevent.

A written correction would rot the same way, so these tests are the
mechanical barrier: the verb must exist, and no source file may quote
the dead one.
"""

import subprocess
import sys
from pathlib import Path

# tests/scitex_dev/linter/_cmds/ -> repo root is four levels up.
_SRC = Path(__file__).resolve().parents[4] / "src" / "scitex_dev"

_DEAD_VERB = "linter rules --json"


def test_list_rules_verb_is_registered_on_the_linter_group():
    # Arrange
    from scitex_dev.linter.cli import main_group

    # Act
    registered = set(main_group.commands)

    # Assert
    assert "list-rules" in registered


def test_no_source_file_quotes_the_nonexistent_rules_verb():
    # Arrange
    candidates = [
        path
        for path in _SRC.rglob("*")
        if path.suffix in (".py", ".md") and "__pycache__" not in path.parts
    ]

    # Act
    offenders = [
        str(path.relative_to(_SRC))
        for path in candidates
        if _DEAD_VERB in path.read_text(encoding="utf-8", errors="replace")
    ]

    # Assert
    assert offenders == []


def test_dead_verb_really_is_rejected_by_the_cli():
    # Arrange
    argv = [sys.executable, "-m", "scitex_dev", "linter", "rules", "--json"]

    # Act
    completed = subprocess.run(argv, capture_output=True, text=True)

    # Assert
    assert completed.returncode == 2


# EOF
