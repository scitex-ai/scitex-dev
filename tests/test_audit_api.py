"""Tests for the Python API auditor (`scitex-dev quality audit-api`).

Each rule has at least one positive (rule fires on bad fixture) and one
negative (clean fixture passes). Fixtures are inline strings parsed via the
internal `_audit_init` entry point — we don't need to install a fake
distribution to exercise the static checks.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli_audit_api._audit import RULES, _audit_init


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
    expected = {
        "PA101",
        "PA102",
        "PA103",
        "PA104",
        "PA201",
        "PA202",
        "PA203",
        "PA301",
        "PA501",
    }
    assert expected == set(RULES)


# --- §1 Naming and visibility -----------------------------------------------


def test_PA101_missing_all(tmp_path):
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    assert "PA101" in _codes(_audit_init(init, "fakepkg"))


def test_PA102_unbound_name_in_all(tmp_path):
    body = (
        "from __future__ import annotations\n"
        "__version__ = '0.0.0+local'\n"
        "__all__ = ['__version__', 'ghost']\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA102" in _codes(_audit_init(init, "fakepkg"))


def test_PA103_private_name_in_all(tmp_path):
    body = (
        "from __future__ import annotations\n"
        "__version__ = '0.0.0+local'\n"
        "_secret = 1\n"
        "__all__ = ['__version__', '_secret']\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA103" in _codes(_audit_init(init, "fakepkg"))


def test_PA104_third_party_in_all(tmp_path):
    body = (
        "from __future__ import annotations\n"
        "from numpy import ndarray\n"
        "__version__ = '0.0.0+local'\n"
        "__all__ = ['__version__', 'ndarray']\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA104" in _codes(_audit_init(init, "fakepkg"))


# --- §2 Version strategy -----------------------------------------------------


def test_PA201_version_missing_from_all(tmp_path):
    body = (
        "from __future__ import annotations\n"
        "from importlib.metadata import version\n"
        "__version__ = version('fakepkg')\n"
        "__all__ = []\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA201" in _codes(_audit_init(init, "fakepkg"))


def test_PA202_bare_string_version(tmp_path):
    body = (
        "from __future__ import annotations\n"
        "__version__ = '1.2.3'\n"
        "__all__ = ['__version__']\n"
    )
    init = _write_init(tmp_path, body)
    codes = _codes(_audit_init(init, "fakepkg"))
    assert "PA202" in codes
    assert "PA203" in codes  # fallback string is not '0.0.0+local'


def test_PA203_clean_when_canonical_fallback(tmp_path):
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
    # PA203 must NOT fire because the fallback equals the canonical local segment.
    codes = _codes(_audit_init(init, "fakepkg"))
    assert "PA203" not in codes


# --- §3 Lazy imports ---------------------------------------------------------


def test_PA301_top_level_optional_import(tmp_path):
    body = (
        "from __future__ import annotations\n"
        "import h5py\n"  # third-party, top-level — drift
        "__version__ = '0.0.0+local'\n"
        "__all__ = ['__version__']\n"
    )
    init = _write_init(tmp_path, body)
    assert "PA301" in _codes(_audit_init(init, "fakepkg"))


def test_PA301_clean_when_wrapped(tmp_path):
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
    assert "PA301" not in _codes(_audit_init(init, "fakepkg"))


# --- §5 Type hints -----------------------------------------------------------


def test_PA501_missing_future_annotations(tmp_path):
    body = "__version__ = '0.0.0+local'\n__all__ = ['__version__']\n"
    init = _write_init(tmp_path, body)
    assert "PA501" in _codes(_audit_init(init, "fakepkg"))


# --- Negative: a fully canonical __init__.py passes -------------------------


def test_canonical_init_has_no_violations(tmp_path):
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
