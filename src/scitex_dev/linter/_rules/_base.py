"""Rule dataclass definition."""

from dataclasses import dataclass

# Rule scopes — WHERE a rule may fire. The engine applies the scope
# uniformly to every finding (engine call rules AND plugin checkers), so a
# leaf plugin declares its false-positive gate instead of re-implementing it.
#
# - SCOPE_ANY ("")                       — every linted file (the default).
# - SCOPE_RESEARCH_SCRIPT ("research-script") — only research scripts: a
#   module declaring an ``@stx.session`` / ``@stx.module`` entry point, or a
#   file under a configured ``script_dirs`` entry of a ``project-type:
#   research`` project; never test files. See ``_research_scope.py``.
SCOPE_ANY = ""
SCOPE_RESEARCH_SCRIPT = "research-script"
SCOPES = frozenset({SCOPE_ANY, SCOPE_RESEARCH_SCRIPT})


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str  # "error", "warning", "info"
    category: str  # "structure", "import", "io", "plot", "stats"
    message: str
    suggestion: str
    requires: str = ""
    scope: str = SCOPE_ANY  # one of SCOPES; enforced by the engine
