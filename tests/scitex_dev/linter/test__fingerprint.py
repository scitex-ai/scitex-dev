"""Rule-set + findings fingerprint: identical trees agree, any change shows."""

from __future__ import annotations

from scitex_dev.linter._fingerprint import diff_fingerprints, fingerprint_paths

SCRIPT = "import mock\n"


def _corpus(tmp_path, text=SCRIPT):
    root = tmp_path / "corpus"
    (root / "run_out").mkdir(parents=True)
    (root / "tool.py").write_text(text, encoding="utf-8")
    # Session output trees are products of the corpus, not part of it.
    (root / "run_out" / "ignored.py").write_text("import mock\n", encoding="utf-8")
    return root


def test_fingerprint_records_each_corpus_file_hash(tmp_path):
    # Arrange
    root = _corpus(tmp_path)
    # Act
    fp = fingerprint_paths([root])
    # Assert
    assert list(fp["corpus"]) == [str((root / "tool.py").resolve())]


def test_fingerprint_records_engine_finding(tmp_path):
    # Arrange
    root = _corpus(tmp_path)
    # Act
    fp = fingerprint_paths([root])
    # Assert
    assert "STX-NM001" in {f[3] for f in fp["findings"]}


def test_fingerprint_of_same_tree_has_no_difference(tmp_path):
    # Arrange
    root = _corpus(tmp_path)
    # Act
    diff = diff_fingerprints(fingerprint_paths([root]), fingerprint_paths([root]))
    # Assert
    assert diff == {}


def test_fingerprint_difference_names_changed_findings(tmp_path):
    # Arrange
    root = _corpus(tmp_path)
    before = fingerprint_paths([root])
    (root / "tool.py").write_text("x = 1\n", encoding="utf-8")
    # Act
    diff = diff_fingerprints(before, fingerprint_paths([root]))
    # Assert
    assert {"corpus", "findings"} <= set(diff)


def test_fingerprint_difference_ignores_rule_owner_changes():
    # Arrange
    base = {"rules": {}, "findings": [], "errors": [], "corpus": {}}
    # Act
    diff = diff_fingerprints(
        {**base, "owners": {"STX-X": "engine"}}, {**base, "owners": {"STX-X": "leaf"}}
    )
    # Assert
    assert diff == {}
