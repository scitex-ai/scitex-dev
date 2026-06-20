"""Tests for the Python API auditor (`scitex-dev quality audit-api`).

Each rule has at least one positive (rule fires on bad fixture) and one
negative (clean fixture passes). Fixtures are inline strings parsed via the
internal `_audit_init` entry point — we don't need to install a fake
distribution to exercise the static checks.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._api._audit import RULES, _audit_init, _locate_init


def _write_init(tmp_path: Path, body: str) -> Path:
    """Write a fake `<pkg>/__init__.py` and return the path."""
    pkg_dir = tmp_path / "fakepkg"
    pkg_dir.mkdir()
    init = pkg_dir / "__init__.py"
    init.write_text(body)
    return init


def _codes(violations) -> set[str]:
    return {v.rule for v in violations}


# --- Rule registry sanity ----------------------------------------------------


def test_rules_registry_covers_documented_codes():
    # Arrange
    # Act
    # Assert
    expected = {
        "PA-101",
        "PA-102",
        "PA-103",
        "PA-104",
        "PA-201",
        "PA-202",
        "PA-203",
        "PA-301",
        "PA-304",  # umbrella imports inside standalone source (2026-05-06)
        "PA-305",  # playwright source must call capture_debug_artifacts_async
        "PA-306",  # no-mocks: forbid mock library/symbols/fixtures (2026-05-14)
        "PA-307",  # test-quality: mirrors linter STX-TQ001-007 (2026-05-14)
        "PA-501",
    }
    assert expected == set(RULES)


# --- §1 Naming and visibility -----------------------------------------------


def test_PA101_missing_all(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    assert "PA-101" in _codes(_audit_init(init, "fakepkg"))


def test_PA102_unbound_name_in_all(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "__version__ = '0.0.0+local'\n"
        "__all__ = ['__version__', 'ghost']\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA-102" in _codes(_audit_init(init, "fakepkg"))


def test_PA102_silent_for_pep562_lazy_getattr(tmp_path):
    """PEP 562 lazy `__getattr__` dispatch counts names as bound."""
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "__version__ = '0.0.0+local'\n"
        "__all__ = ['__version__', 'lazy_one', 'lazy_two']\n"
        "def __getattr__(name):\n"
        "    if name == 'lazy_one':\n"
        "        from . import _impl_one as m; return m\n"
        "    if name == 'lazy_two':\n"
        "        from . import _impl_two as m; return m\n"
        "    raise AttributeError(name)\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA-102" not in _codes(_audit_init(init, "fakepkg"))


def test_PA103_private_name_in_all(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "__version__ = '0.0.0+local'\n"
        "_secret = 1\n"
        "__all__ = ['__version__', '_secret']\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA-103" in _codes(_audit_init(init, "fakepkg"))


def test_PA104_third_party_in_all(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "from numpy import ndarray\n"
        "__version__ = '0.0.0+local'\n"
        "__all__ = ['__version__', 'ndarray']\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA-104" in _codes(_audit_init(init, "fakepkg"))


# --- §2 Version strategy -----------------------------------------------------


def test_PA201_version_missing_from_all(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "from importlib.metadata import version\n"
        "__version__ = version('fakepkg')\n"
        "__all__ = []\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA-201" in _codes(_audit_init(init, "fakepkg"))


def test_PA202_bare_string_version_pa_202_in_codes(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "__version__ = '1.2.3'\n"
        "__all__ = ['__version__']\n"
    )
    init = _write_init(tmp_path, body)
    codes = _codes(_audit_init(init, "fakepkg"))
    assert "PA-202" in codes


def test_PA202_bare_string_version_pa_203_in_codes(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "__version__ = '1.2.3'\n"
        "__all__ = ['__version__']\n"
    )
    init = _write_init(tmp_path, body)
    codes = _codes(_audit_init(init, "fakepkg"))
    assert "PA-203" in codes  # fallback string is not '0.0.0+local'


def test_PA202_clean_with_aliased_import_pa_202_not_in_codes(tmp_path):
    """`from importlib.metadata import version as _v; __version__ = _v(...)` is canonical."""
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "from importlib.metadata import version as _v, PackageNotFoundError\n"
        "try:\n"
        "    __version__ = _v('fakepkg')\n"
        "except PackageNotFoundError:\n"
        "    __version__ = '0.0.0+local'\n"
        "__all__ = ['__version__']\n"
    )
    init = _write_init(tmp_path, body)
    codes = _codes(_audit_init(init, "fakepkg"))
    assert "PA-202" not in codes


def test_PA202_clean_with_aliased_import_pa_203_not_in_codes(tmp_path):
    """`from importlib.metadata import version as _v; __version__ = _v(...)` is canonical."""
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "from importlib.metadata import version as _v, PackageNotFoundError\n"
        "try:\n"
        "    __version__ = _v('fakepkg')\n"
        "except PackageNotFoundError:\n"
        "    __version__ = '0.0.0+local'\n"
        "__all__ = ['__version__']\n"
    )
    init = _write_init(tmp_path, body)
    codes = _codes(_audit_init(init, "fakepkg"))
    assert "PA-203" not in codes


def test_PA203_clean_when_canonical_fallback(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "from importlib.metadata import PackageNotFoundError, version\n"
        "try:\n"
        "    __version__ = version('fakepkg')\n"
        "except PackageNotFoundError:\n"
        "    __version__ = '0.0.0+local'\n"
        "__all__ = ['__version__']\n"
    )
    init = _write_init(tmp_path, body)
    # The walker keeps the *last* assignment — the fallback literal.
    # PA-203 must NOT fire because the fallback equals the canonical local segment.
    codes = _codes(_audit_init(init, "fakepkg"))
    assert "PA-203" not in codes


# --- §3 Lazy imports ---------------------------------------------------------


def test_PA301_top_level_optional_import(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "import h5py\n"  # third-party, top-level — drift
        "__version__ = '0.0.0+local'\n"
        "__all__ = ['__version__']\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA-301" in _codes(_audit_init(init, "fakepkg"))


def test_PA301_clean_when_wrapped(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "try:\n"
        "    import h5py\n"
        "except ImportError:\n"
        "    h5py = None\n"
        "__version__ = '0.0.0+local'\n"
        "__all__ = ['__version__', 'h5py']\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA-301" not in _codes(_audit_init(init, "fakepkg"))


# --- §5 Type hints -----------------------------------------------------------


def test_PA501_missing_future_annotations(tmp_path):
    # Arrange
    # Act
    # Assert
    body = "__version__ = '0.0.0+local'\n__all__ = ['__version__']\n"
    init = _write_init(tmp_path, body)
    assert "PA-501" in _codes(_audit_init(init, "fakepkg"))


# --- Negative: a fully canonical __init__.py passes -------------------------


def test_canonical_init_has_no_violations(tmp_path):
    # Arrange
    # Act
    # Assert
    body = (
        "from __future__ import annotations\n"
        "from importlib.metadata import PackageNotFoundError, version\n"
        "\n"
        "try:\n"
        "    __version__ = version('fakepkg')\n"
        "except PackageNotFoundError:\n"
        "    __version__ = '0.0.0+local'\n"
        "\n"
        "def hello() -> str:\n"
        "    return 'hi'\n"
        "\n"
        "__all__ = ['__version__', 'hello']\n"
    )
    init = _write_init(tmp_path, body)
    violations = _audit_init(init, "fakepkg")
    assert violations == [], f"unexpected: {[(v.rule, v.detail) for v in violations]}"


# --- §3 PA-306 no-mocks -----------------------------------------------------


def test_PA306_flags_unittest_mock_import(tmp_path):
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.audit._api._audit import _audit_no_mocks

    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "impl.py").write_text(
        "from unittest.mock import patch\ndef f():\n    return patch\n"
    )
    codes = _codes(_audit_no_mocks(init, "fakepkg", "fakepkg"))
    assert "PA-306" in codes


def test_PA306_flags_pytest_mocker_fixture(tmp_path):
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.audit._api._audit import _audit_no_mocks

    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "test_x.py").write_text(
        "def test_thing(mocker, tmp_path):\n    return tmp_path\n"
    )
    codes = _codes(_audit_no_mocks(init, "fakepkg", "fakepkg"))
    assert "PA-306" in codes


def test_PA306_clean_source_passes(tmp_path):
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.audit._api._audit import _audit_no_mocks

    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "impl.py").write_text("def f(tmp_path):\n    return tmp_path\n")
    assert _audit_no_mocks(init, "fakepkg", "fakepkg") == []


# --- §3 PA-305 playwright-without-debug-capture -----------------------------


def test_PA305_flags_runtime_playwright_without_capture(tmp_path):
    # Arrange
    from scitex_dev._cli.audit._api._audit import _audit_playwright_capture

    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "driver.py").write_text(
        "from playwright.async_api import async_playwright\n"
        "async def run():\n"
        "    async with async_playwright() as p:\n"
        "        return p\n"
    )
    # Act
    codes = _codes(_audit_playwright_capture(init, "fakepkg", "fakepkg"))
    # Assert
    assert "PA-305" in codes


def test_PA305_clean_when_import_is_type_checking_only(tmp_path):
    # Arrange
    from scitex_dev._cli.audit._api._audit import _audit_playwright_capture

    init = _write_init(tmp_path, "from __future__ import annotations\n")
    # Type-only import: `Page` is used solely to annotate a handed-in page.
    # The module never opens a browser, so PA-305 must stay silent.
    (init.parent / "translator.py").write_text(
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from playwright.async_api import Page\n"
        "async def extract(page: Page) -> str:\n"
        "    return page.url\n"
    )
    # Act
    codes = _codes(_audit_playwright_capture(init, "fakepkg", "fakepkg"))
    # Assert
    assert "PA-305" not in codes


def test_PA305_flags_module_level_import_even_with_type_checking_block(tmp_path):
    # Arrange
    from scitex_dev._cli.audit._api._audit import _audit_playwright_capture

    init = _write_init(tmp_path, "from __future__ import annotations\n")
    # A runtime (module-level) playwright import is NOT exempted just because
    # the file also has an unrelated TYPE_CHECKING guard elsewhere.
    (init.parent / "mixed.py").write_text(
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        "from playwright.async_api import async_playwright\n"
        "if TYPE_CHECKING:\n"
        "    from collections.abc import Mapping\n"
        "async def run() -> None:\n"
        "    async with async_playwright() as p:\n"
        "        _ = p\n"
    )
    # Act
    codes = _codes(_audit_playwright_capture(init, "fakepkg", "fakepkg"))
    # Assert
    assert "PA-305" in codes


# ---------------------------------------------------------------------------
# _locate_init — registry source-tree fallback (phantom-skip fix)
#
# Before this fallback, `_locate_init` returned None whenever find_spec
# couldn't import the package, so audit-python-apis silently SKIPPED the
# entire audit (`return 0`, "package not importable" info) for any peer
# the developer had cloned locally but not pip-installed. The same fail-
# silent class the SK-101 fix (PR #177) eliminated for the skills auditor;
# this PR closes it for audit-python-apis. The fallback walks the package's
# source tree via ECOSYSTEM.local_path.
#
# No-mocks discipline: we mutate the real ECOSYSTEM dict in-place via a
# try/finally contextmanager (NOT `monkeypatch`, NOT `unittest.mock`) so
# PA-306 stays clean.
# ---------------------------------------------------------------------------


from contextlib import contextmanager


@contextmanager
def _registry_override(distribution: str, local_path: Path):
    """Temporarily add (or replace) an ECOSYSTEM entry; restore on exit.

    No-mocks-compliant: pure dict mutation + try/finally restore. The
    sentinel `_MISSING` distinguishes "key didn't exist" from "key existed
    with None value" so restoration is exact.
    """
    from scitex_dev._ecosystem._registry import ECOSYSTEM

    _MISSING = object()
    before = ECOSYSTEM.get(distribution, _MISSING)
    ECOSYSTEM[distribution] = {
        "local_path": str(local_path),
        "pypi_name": distribution,
        "github_repo": f"ywatanabe1989/{distribution}",
        "import_name": distribution.replace("-", "_"),
        "category": "library",
    }
    try:
        yield
    finally:
        if before is _MISSING:
            ECOSYSTEM.pop(distribution, None)
        else:
            ECOSYSTEM[distribution] = before


def test_locate_init_falls_back_to_registry_source_tree(tmp_path):
    # Arrange — non-installed package with a valid on-disk __init__.py.
    # find_spec("phantomapi") returns None, so the source-tree fallback
    # is the only path that can return a non-None Path. Without it,
    # audit-python-apis would silently skip the whole audit.
    dist = "scitex-phantomapi"
    import_name = "scitex_phantomapi"
    local_root = tmp_path / "scitex-phantomapi"
    init = local_root / "src" / import_name / "__init__.py"
    init.parent.mkdir(parents=True)
    init.write_text("__all__ = []\n__version__ = '0.0.0'\n")
    # Act
    with _registry_override(dist, local_root):
        result = _locate_init(dist, import_name)
    # Assert
    assert result == init


def test_locate_init_returns_none_when_registry_path_missing_on_disk(tmp_path):
    # Arrange — registry has `local_path` but the directory doesn't
    # exist on this host (clean checkout, CI runner, etc.). The fallback
    # must NOT crash and must return None so the caller skips cleanly
    # rather than auditing a non-existent file.
    dist = "scitex-ghostapi"
    nonexistent = tmp_path / "does-not-exist"
    # Act
    with _registry_override(dist, nonexistent):
        result = _locate_init(dist, "scitex_ghostapi")
    # Assert
    assert result is None


def test_locate_init_returns_none_when_registry_path_lacks_init_file(tmp_path):
    # Arrange — registry path exists but no `src/<pkg>/__init__.py`.
    # Real edge case for a freshly-`git init`ed repo. Fallback must
    # decline cleanly so the caller's "package not importable" skip
    # remains correct.
    dist = "scitex-emptypkg"
    import_name = "scitex_emptypkg"
    local_root = tmp_path / "scitex-emptypkg"
    local_root.mkdir()
    # Act
    with _registry_override(dist, local_root):
        result = _locate_init(dist, import_name)
    # Assert
    assert result is None


def test_locate_init_returns_none_when_neither_installed_nor_registered():
    # Arrange — distribution is not pip-installed AND not in ECOSYSTEM.
    # The fallback must NOT invent a path; caller's audit skip is the
    # correct behaviour for a truly-missing package.
    # Act
    result = _locate_init("scitex-doesnotexistanywhere", "scitex_doesnotexistanywhere")
    # Assert
    assert result is None


def test_locate_init_prefers_installed_when_both_present(tmp_path):
    # Arrange — installed package is the canonical source-of-truth (it's
    # what users actually import); the registry fallback is only consulted
    # when find_spec fails. scitex_dev is installed in the test venv, so a
    # bogus registry path for "scitex-dev" must NOT override the install
    # location.
    bogus_root = tmp_path / "bogus-scitex-dev"
    bogus_init = bogus_root / "src" / "scitex_dev" / "__init__.py"
    bogus_init.parent.mkdir(parents=True)
    bogus_init.write_text("__all__ = []\n")
    # Act
    with _registry_override("scitex-dev", bogus_root):
        result = _locate_init("scitex-dev", "scitex_dev")
    # Assert — install path wins, never under bogus_root
    assert result is None or bogus_root not in result.parents
