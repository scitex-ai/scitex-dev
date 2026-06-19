"""Mirror tests for `_checks/_playwright.py` — PA-305 capture-discipline audit.

A runtime `playwright.async_api` import without a debug-capture call trips
PA-305; a `TYPE_CHECKING`-guarded import does not. `_type_checking_import_node_ids`
collects the guarded import node ids. Real source via `tmp_path` / `ast`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from scitex_dev._cli.audit._api._checks._playwright import (
    _audit_playwright_capture,
    _type_checking_import_node_ids,
)


def _write_init(tmp_path: Path, body: str) -> Path:
    pkg_dir = tmp_path / "fakepkg"
    pkg_dir.mkdir()
    init = pkg_dir / "__init__.py"
    init.write_text(body)
    return init


def test_audit_playwright_flags_runtime_import_without_capture(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "driver.py").write_text(
        "from playwright.async_api import async_playwright\n"
        "async def run():\n"
        "    async with async_playwright() as p:\n"
        "        return p\n"
    )
    codes = {v.rule for v in _audit_playwright_capture(init, "fakepkg", "fakepkg")}
    assert "PA-305" in codes


def test_audit_playwright_silent_for_type_checking_only_import(tmp_path):
    # Arrange
    # Act
    # Assert
    init = _write_init(tmp_path, "from __future__ import annotations\n")
    (init.parent / "translator.py").write_text(
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from playwright.async_api import Page\n"
        "async def extract(page: Page) -> str:\n"
        "    return page.url\n"
    )
    codes = {v.rule for v in _audit_playwright_capture(init, "fakepkg", "fakepkg")}
    assert "PA-305" not in codes


def test_type_checking_import_node_ids_collects_guarded_imports():
    # Arrange
    # Act
    # Assert
    tree = ast.parse(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from x import Y\n"
    )
    assert len(_type_checking_import_node_ids(tree)) >= 1
