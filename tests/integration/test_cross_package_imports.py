"""Runtime cross-package import gate (auto-generated).

Regenerate with `scitex-dev ecosystem install-cross-package-gate scitex-dev
--force`. Hand edits inside the AUTO-GENERATED block will be overwritten;
add hand-written cases below the second sentinel, where they are preserved
byte-identically.

(This line previously credited `ecosystem write-integration-tests`, a command
that has never existed — fossil text from a one-shot script since deleted,
carried by 17 files fleet-wide.)

This test imports every cross-package module that 'scitex-dev' references
in its source tree. Three outcomes:

- Module installed AND import succeeds → test PASSES.
- Peer standalone installed BUT the path is broken (e.g. the rename
  `scitex_io._load_cache` → `scitex_io._loading._load_cache`) →
  test FAILS loudly.
- Peer standalone NOT installed at all (absent in this CI env) →
  test is SKIPPED.

That second outcome is the reason this gate exists, and until 2026-08-16 it
did not hold: the skip was taken on the FULL dotted path, so a rename raised
ModuleNotFoundError, was skipped, and reported green. The skip is now taken
on the ROOT only — see `_import_peer` below.
"""

import importlib

import pytest

# ===== AUTO-GENERATED: cross-package imports =====
CROSS_PACKAGE_IMPORTS = [
    "scitex",
    "scitex._mcp_tools",
    "scitex_cards",
    "scitex_cards._paths",
    "scitex_cards._store",
    "scitex_config",
    "scitex_config._ecosystem",
    "scitex_events",
    "scitex_logging",
]
# ===== END AUTO-GENERATED =====


def _import_peer(module_name):
    """Skip when the PEER is absent; FAIL when the PATH is broken.

    These are different states and `importorskip(module_name)` collapsed them.
    It skips on any ImportError, and a renamed submodule raises
    ModuleNotFoundError — an ImportError subclass — so the rename this gate
    exists to catch was SKIPPED and reported green. Measured 2026-08-16: all
    19 gates in the fleet were in that state, this one included, while this
    file's own docstring promised such a case "FAILS loudly".

    Skipping on the ROOT keeps the legitimate case (the peer standalone is
    genuinely not installed in this CI) and restores the loud failure for the
    case that matters.
    """
    pytest.importorskip(module_name.split(".")[0])
    return importlib.import_module(module_name)


@pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)
def test_cross_package_import_returns_non_none_module(module_name):
    # Arrange
    # Act
    mod = _import_peer(module_name)
    # Assert
    assert mod is not None


#: Roots reached through a compat-ALIAS shim, where ``__name__`` reports the
#: CANONICAL module rather than the name that was requested — by design.
#:
#: scitex-cards ruled on this 2026-07-29, and the ruling is the right one:
#: ``__name__`` stays truthful. It is load-bearing far beyond this assertion
#: (tracebacks, ``logging.getLogger(__name__)`` hierarchies, pickle class
#: resolution, ``sys.modules`` identity reasoning), and a shim is where a
#: lying ``__name__`` would be MOST dangerous, because a reader debugging it
#: already is not sure which code is running.
#:
#: So this is not a defect to route around — the assertion simply encodes an
#: assumption the scitex-todo -> scitex-cards rename invalidated. It is
#: SKIPPED rather than RELAXED on scitex-cards' argument: a relaxed assertion
#: is the check quietly deleted, whereas a skip with a reason is a visible IOU
#: that fails loudly the day someone removes it for the wrong reason.
#:
#: Replace with the real check when ``scitex_cards._compat_aliases`` lands
#: (``resolve_alias(name)`` -> canonical, else None). The property to assert is
#: then "the module I got is either the name I asked for, or its declared
#: canonical form" — which stays true through the shim's removal, at which
#: point ``importorskip`` skips these again and the test goes quiet on its own.
_ALIAS_ROOTS_PENDING_DECLARED_MAP = {"scitex_todo": "scitex_cards"}


def _import_unless_alias(module_name):
    """Import ``module_name``, skipping the declared compat aliases.

    Both exits live here rather than in the test body so that Act stays one
    statement and the test keeps exactly one assertion (STX-TQ007 counts
    every test-terminating ``pytest`` call, not just ``assert``).
    """
    canonical = _ALIAS_ROOTS_PENDING_DECLARED_MAP.get(module_name.split(".", 1)[0])
    if canonical is not None:
        pytest.skip(
            f"{module_name} resolves through the {canonical} compat-alias "
            f"shim, so __name__ reports {canonical}.* by design. Awaiting "
            "scitex_cards._compat_aliases.resolve_alias to assert the real "
            "property; see _ALIAS_ROOTS_PENDING_DECLARED_MAP above."
        )
    return _import_peer(module_name)


@pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)
def test_cross_package_import_module_name_matches_request(module_name):
    # Arrange
    # Act
    mod = _import_unless_alias(module_name)
    # Assert
    assert getattr(mod, "__name__", "") == module_name


@pytest.mark.parametrize("module_name", CROSS_PACKAGE_IMPORTS)
def test_cross_package_import_module_has_real_spec(module_name):
    # Real modules always set `__spec__` (PEP 451). Catches the case
    # where something injected a `types.SimpleNamespace` into sys.modules.
    # Arrange
    # Act
    mod = _import_peer(module_name)
    # Assert
    assert mod.__spec__ is not None
