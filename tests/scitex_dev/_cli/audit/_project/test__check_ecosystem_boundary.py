# -*- coding: utf-8 -*-
"""Tests for `_check_ecosystem_boundary.py` (PS-183 — ADR-0003 a2 smell).

PS-183 flags an UNGUARDED, TOP-LEVEL import from this leaf package into
ANOTHER leaf package's PRIVATE internals, when the peer is NOT a
foundational-tier package. Per the ADR-0003 methodology caveat, a static
scan can't tell a hard dependency from a guarded one, so the check must
skip: try/except-guarded imports, lazy (function-body) imports, and
TYPE_CHECKING-only imports. Real temp packages, no mocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_ecosystem_boundary import (
    check_ps183_ecosystem_boundary,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _codes(out: list) -> set[str]:
    return {v.rule for v in out}


def _make_pkg(tmp_path: Path, *, dist: str, src_body: str) -> Path:
    repo = tmp_path / dist
    _write(repo / "pyproject.toml", f'[project]\nname = "{dist}"\n')
    import_name = dist.replace("-", "_")
    _write(repo / "src" / import_name / "__init__.py", "")
    _write(repo / "src" / import_name / "_core.py", src_body)
    return repo


# --- genuine a2 violation: hard top-level private cross-import -------------


def test_ps183_fires_for_hard_top_level_private_cross_import(tmp_path):
    # Arrange — unguarded top-level `from scitex_peer._private import X`
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body="from scitex_peer._private_helpers import do_thing\n",
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert "PS-183" in _codes(out)


def test_ps183_fires_for_hard_top_level_private_attribute_import(tmp_path):
    # Arrange — `from scitex_peer import _private_attr` (public module,
    # private NAME) is also the a2 smell.
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body="from scitex_peer import _load_cache\n",
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert "PS-183" in _codes(out)


def test_ps183_detail_names_the_offending_peer(tmp_path):
    # Arrange — same shape; verify the detail message is useful, separately.
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body="from scitex_peer import _load_cache\n",
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert any("scitex_peer" in v.detail for v in out)


def test_ps183_fires_for_hard_top_level_private_plain_import(tmp_path):
    # Arrange — `import scitex_peer._private_mod` (plain Import form)
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body="import scitex_peer._private_mod\n",
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert "PS-183" in _codes(out)


# --- NOT flagged: try/except-guarded import ---------------------------------


def test_ps183_silent_for_try_except_guarded_import(tmp_path):
    # Arrange — guarded optional import (kind d — ports pattern working)
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body=(
            "try:\n"
            "    from scitex_peer._private_helpers import do_thing\n"
            "except ImportError:\n"
            "    do_thing = None\n"
        ),
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert out == []


def test_ps183_silent_for_bare_except_guarded_import(tmp_path):
    # Arrange — bare `except:` also counts as guarded.
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body=(
            "try:\n"
            "    from scitex_peer._private_helpers import do_thing\n"
            "except:\n"
            "    do_thing = None\n"
        ),
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert out == []


# --- NOT flagged: lazy in-function import ------------------------------------


def test_ps183_silent_for_lazy_in_function_import(tmp_path):
    # Arrange — import lives inside a function body (kind d).
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body=(
            "def use_peer():\n"
            "    from scitex_peer._private_helpers import do_thing\n"
            "    return do_thing()\n"
        ),
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert out == []


# --- NOT flagged: TYPE_CHECKING-only import ----------------------------------


def test_ps183_silent_for_type_checking_only_import(tmp_path):
    # Arrange — `if TYPE_CHECKING:` import has zero runtime edge.
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body=(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from scitex_peer._private_helpers import Thing\n"
        ),
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert out == []


# --- NOT flagged: foundational-tier peer, even if a2-shaped ------------------


def test_ps183_silent_for_foundational_tier_peer_io(tmp_path):
    # Arrange — scitex_io is foundational tier; private reach still fine.
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body="from scitex_io._private_loader import load_cache\n",
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert out == []


def test_ps183_silent_for_foundational_tier_peer_config(tmp_path):
    # Arrange — scitex_config is foundational tier.
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body="import scitex_config._private_internal\n",
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert out == []


# --- NOT flagged: self-import, public surface, non-scitex ------------------


def test_ps183_silent_for_self_import(tmp_path):
    # Arrange — importing your own private submodule is not a cross-import.
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body="from scitex_foo._helper import x\n",
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert out == []


def test_ps183_silent_for_public_surface_cross_import(tmp_path):
    # Arrange — importing a peer's PUBLIC surface is fine (a1/direct import).
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body="from scitex_peer import public_function\n",
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert out == []


def test_ps183_silent_for_third_party_private_import(tmp_path):
    # Arrange — a private-looking import of a non-scitex package is out of
    # scope for this rule entirely.
    repo = _make_pkg(
        tmp_path,
        dist="scitex-foo",
        src_body="from numpy._core import something\n",
    )
    out: list = []
    # Act
    check_ps183_ecosystem_boundary(repo, "scitex-foo", _StubViolation, out)
    # Assert
    assert out == []
