# -*- coding: utf-8 -*-
"""Tests for `_legacy_keys` — diagnostics for keys that mask nothing.

Fleet fact (cards, app): repos declare `audit.skip` / `audit.exemptions`
entries that suppress nothing outside `audit-project`, yet read as done.
These notices name the gap and point at `audit.skip-rules`. Notices, not
findings — counts and exit codes are untouched (covered by the audit
callers, not here).

No mocks — real `config.yaml` files under `tmp_path`. Single assert per
test (PA-307).
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._config._legacy_keys import (
    EXEMPTION_ARMED_RULES,
    legacy_audit_key_notices,
)


def _write_config(repo: Path, body: str) -> Path:
    cfg = repo / ".scitex" / "dev" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(body, encoding="utf-8")
    return repo


class TestAuditSkipNotice:
    def test_skip_list_produces_a_skip_rules_notice(
        self, tmp_path: Path
    ) -> None:
        # Arrange — the cards/app shape: bare rule ids under audit.skip.
        _write_config(
            tmp_path, "project-type:\n  - pip\naudit:\n  skip:\n    - PS-204\n"
        )
        # Act
        notices = legacy_audit_key_notices(tmp_path)
        # Assert
        assert any("audit.skip" in n and "skip-rules" in n for n in notices)

    def test_skip_notice_names_the_listed_rules(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        _write_config(
            tmp_path, "audit:\n  skip:\n    - PS-204\n    - PS-140\n"
        )
        # Act
        notices = legacy_audit_key_notices(tmp_path)
        # Assert
        assert any("PS-204" in n and "PS-140" in n for n in notices)

    def test_no_skip_key_produces_no_skip_notice(
        self, tmp_path: Path
    ) -> None:
        # Arrange — the common case stays silent.
        _write_config(tmp_path, "project-type:\n  - pip\n")
        # Act
        notices = legacy_audit_key_notices(tmp_path)
        # Assert
        assert not any("audit.skip" in n for n in notices)


class TestDeadExemptionNotice:
    def test_exemption_for_an_unarmed_rule_is_dead(
        self, tmp_path: Path
    ) -> None:
        # Arrange — app's PS-210 trap: no check consults exemptions for
        # PS-210, so the entry suppresses nothing.
        _write_config(
            tmp_path,
            "audit:\n  exemptions:\n    PS-210:\n"
            "      - path: pyproject.toml\n        line: 0\n"
            '        reason: "dev set is a PEP 735 group"\n',
        )
        # Act
        notices = legacy_audit_key_notices(tmp_path)
        # Assert
        assert any("PS-210" in n and "skip-rules" in n for n in notices)

    def test_exemption_for_an_armed_rule_is_silent(
        self, tmp_path: Path
    ) -> None:
        # Arrange — negative control: PS-231 has an exemption arm, so a
        # reasoned entry there is live config, not dead.
        _write_config(
            tmp_path,
            "audit:\n  exemptions:\n    PS-231:\n"
            "      - path: .github/workflows/x.yml\n        line: 0\n"
            '        reason: "status-context sequencing"\n',
        )
        # Act
        notices = legacy_audit_key_notices(tmp_path)
        # Assert
        assert notices == []

    def test_non_mapping_exemptions_block_is_dead(
        self, tmp_path: Path
    ) -> None:
        # Arrange — the hub-2026-07-29 shape: a list block the parser
        # drops wholesale.
        _write_config(
            tmp_path,
            "audit:\n  exemptions:\n    - rule: PS-224\n",
        )
        # Act
        notices = legacy_audit_key_notices(tmp_path)
        # Assert
        assert any("audit.exemptions" in n for n in notices)


class TestArmedSetIsPinned:
    def test_every_armed_rule_has_a_real_consumer(self) -> None:
        # Arrange — the set must equal the checks that actually consult
        # `exemption_for` to suppress. Both call shapes count: a literal
        # rule (`exemption_for("PS-221", …)`) and the `_RULE` constant in
        # a module that calls `exemption_for(` with it. A drifted list
        # either silences a live arm's users or cries dead over live
        # config.
        # Act
        import re

        root = Path(__file__).resolve().parents[5] / "src" / "scitex_dev"
        consumers: set[str] = set()
        for path in (root / "_cli" / "audit").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "exemption_for(" not in text:
                continue
            consumers.update(
                re.findall(r"exemption_for\(\s*[\"']([^\"']+)[\"']", text)
            )
            consumers.update(
                re.findall(r"_RULE\s*=\s*[\"']([^\"']+)[\"']", text)
            )
        # Assert
        assert consumers == set(EXEMPTION_ARMED_RULES)


# EOF
