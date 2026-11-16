"""Research-script scope gate + per-project-type plugin requirements.

Two engine-level guarantees that leaf plugins rely on (plugin SPI, see
``spi.py`` and the ``08_linter-plugins`` skill):

1. **One false-positive gate.** A rule declaring
   ``scope="research-script"`` fires only in research scripts. The engine
   decides that ONCE per file, after the whole module is visited (an
   ``@stx.session def main`` usually sits BELOW the helpers that do the
   I/O), and drops out-of-scope findings from engine call rules and plugin
   checkers alike. Leaf plugins therefore never re-implement the gate.

2. **Fail loud on missing coverage.** A ``project-type: research`` project
   depends on coverage that only leaf plugins provide (raw-file-I/O
   detection is owned by scitex-io). A plugin declares what it covers via
   the payload key ``capabilities``; when a required capability is absent
   the engine raises ``LinterPluginError`` instead of reporting a clean run
   on a reduced rule corpus.
"""

from __future__ import annotations

from pathlib import Path

from ._rules._base import SCOPE_RESEARCH_SCRIPT

__all__ = [
    "REQUIRED_CAPABILITIES",
    "apply_scopes",
    "check_required_capabilities",
    "is_research_script",
    "is_test_file",
]

# project-type -> {capability: the distribution (with floor) that provides it}
REQUIRED_CAPABILITIES = {
    "research": {"raw-io": "scitex-io>=0.5.0"},
}


def is_test_file(filepath: str) -> bool:
    """True for pytest files and anything under a ``tests``/``test`` dir."""
    p = Path(filepath)
    name = p.name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or any(seg in {"tests", "test"} for seg in p.parts)
    )


def is_research_script(filepath: str, config, *, has_entry_decorator: bool) -> bool:
    """Whether *filepath* is a research script (the ``research-script`` scope).

    True when the file is not a test file AND either declares an
    ``@stx.session`` / ``@stx.module`` entry point (*has_entry_decorator*)
    or lives under a configured ``script_dirs`` entry of a
    ``project-type: research`` project. Library code (``src/``) without an
    entry point is never a research script.
    """
    if is_test_file(filepath):
        return False
    if has_entry_decorator:
        return True
    research = "research" in (getattr(config, "project_types", None) or ())
    script_dirs = getattr(config, "script_dirs", None) or ()
    parts = Path(filepath).parts
    return research and any(d in parts for d in script_dirs)


def apply_scopes(issues: list, *, research_script: bool) -> list:
    """Drop findings whose rule scope excludes this file."""
    if research_script:
        return issues
    return [i for i in issues if getattr(i.rule, "scope", "") != SCOPE_RESEARCH_SCRIPT]


def check_required_capabilities(config, capabilities) -> None:
    """Raise ``LinterPluginError`` when the project type needs a missing plugin.

    *capabilities* maps capability name -> declaring provider (the
    ``load_plugins()["capabilities"]`` view).
    """
    project_types = getattr(config, "project_types", None) or ()
    missing = []
    for ptype in project_types:
        for cap, dist in REQUIRED_CAPABILITIES.get(ptype, {}).items():
            if cap not in capabilities:
                missing.append((ptype, cap, dist))
    if not missing:
        return
    from ._plugin_loader import LinterPluginError

    detail = "; ".join(
        f"project-type {ptype!r} requires linter capability {cap!r} (install `{dist}`)"
        for ptype, cap, dist in missing
    )
    raise LinterPluginError(
        f"{detail}. No installed `scitex_dev.linter.plugins` provider declares "
        "it, so rules this project depends on would silently not run — "
        "refusing to report a clean result on a reduced rule corpus."
    )


# EOF
