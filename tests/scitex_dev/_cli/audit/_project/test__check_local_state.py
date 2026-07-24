"""Tests for `_check_local_state.py` (PS-145 / PS-147).

PS-145 (W) — package source reads ANOTHER scitex package's user-state
             tree (`~/.scitex/<other>/...`) or `SCITEX_<OTHER>_*` env var.
PS-147 (W) — package source writes an eval-form shell-completion line
             (`eval "$(_<NAME>_COMPLETE=bash_source ...)"`) into a user rc
             file.

Both checkers are exercised directly with a stub Violation class against a
`src/<pkg>/` tree in tmp_path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_local_state import (
    check_ps145_cross_package_read,
    check_ps147_eval_form_completion,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write_src(repo: Path, filename: str, body: str) -> None:
    src = repo / "src" / "scitex_demo"
    src.mkdir(parents=True, exist_ok=True)
    (src / filename).write_text(body, encoding="utf-8")


# ===== PS-145 =====

# Reads another package's state dir (`.scitex/io` — a KNOWN short that is
# not this distribution's own).
_CROSS_PACKAGE_READ = 'CACHE = Path.home() / ".scitex/io" / "cache.db"\n'

# Reads only its OWN state dir (`.scitex/demo`) — no cross-package coupling.
_OWN_PACKAGE_READ = 'CACHE = Path.home() / ".scitex/demo" / "cache.db"\n'


class TestPS145CrossPackageRead:
    def test_cross_package_state_read_is_flagged(self, tmp_path: Path) -> None:
        # Arrange
        _write_src(tmp_path, "_paths.py", _CROSS_PACKAGE_READ)
        out: list = []
        # Act
        check_ps145_cross_package_read(
            tmp_path, "scitex-demo", _StubViolation, out
        )
        # Assert
        assert [v.rule for v in out] == ["PS-145"]

    def test_own_package_state_read_produces_no_finding(
        self, tmp_path: Path
    ) -> None:
        # Arrange — control arm: only touches its own .scitex/demo tree
        _write_src(tmp_path, "_paths.py", _OWN_PACKAGE_READ)
        out: list = []
        # Act
        check_ps145_cross_package_read(
            tmp_path, "scitex-demo", _StubViolation, out
        )
        # Assert
        assert out == []


# ===== PS-147 =====

# Writes an eval-form completion line into the user's ~/.bashrc.
_EVAL_COMPLETION = (
    "def install_completion():\n"
    '    rc = Path.home() / ".bashrc"\n'
    "    rc.write_text(\n"
    '        \'eval "$(_DEMO_COMPLETE=bash_source demo)"\\n\'\n'
    "    )\n"
)

# Uses the cache-file completion pattern instead — no eval form.
_CACHE_COMPLETION = (
    "def install_completion():\n"
    '    rc = Path.home() / ".bashrc"\n'
    "    cache = Path.home() / '.scitex/demo/runtime/completion/demo'\n"
    "    rc.write_text(f'[ -f {cache} ] && source {cache}\\n')\n"
)


class TestPS147EvalFormCompletion:
    def test_eval_form_completion_is_flagged(self, tmp_path: Path) -> None:
        # Arrange
        _write_src(tmp_path, "_completion.py", _EVAL_COMPLETION)
        out: list = []
        # Act
        check_ps147_eval_form_completion(tmp_path, _StubViolation, out)
        # Assert
        assert [v.rule for v in out] == ["PS-147"]

    def test_cache_file_completion_produces_no_finding(
        self, tmp_path: Path
    ) -> None:
        # Arrange — control arm: cache-file pattern, no eval form
        _write_src(tmp_path, "_completion.py", _CACHE_COMPLETION)
        out: list = []
        # Act
        check_ps147_eval_form_completion(tmp_path, _StubViolation, out)
        # Assert
        assert out == []
