"""`--version` must not answer confidently when resolution was a coin flip.

Measured in this project's own container, 2026-07-30 — the condition that
motivated this module::

    scitex_dev-0.38.0.dist-info
    scitex_dev-0.38.1.dist-info
    importlib.metadata.version("scitex-dev")  ->  0.38.0   (the OLDER)
    scitex-dev --version                      ->  "scitex-dev 0.38.0"

printed with no marker, while PyPI was at 0.40.4. Two rails probed the same
minute — a bare `import scitex_dev` and `--version` — and BOTH were silent.

These tests seed REAL `.dist-info` directories in a tmp dir and point the
resolver at them via `count_dist_infos`'s `site_packages` seam. No mocks,
and deliberately not the container's own duplication: testing against an
accidental condition would pass for the wrong reason and vanish the moment
someone reinstalls.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli._root_version import AMBIGUOUS_MARKER, resolve_version


def _seed_dist_info(root: Path, name: str, version: str) -> Path:
    """Create a dist-info directory that counts as a real INSTALL."""
    d = root / f"{name}-{version}.dist-info"
    d.mkdir(parents=True)
    (d / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    )
    (d / "RECORD").write_text("")
    return d


def test_two_dist_infos_produce_an_ambiguous_marker(tmp_path):
    """THE positive control — the real container condition, reproduced."""
    # Arrange
    _seed_dist_info(tmp_path, "scitex_dev", "0.38.0")
    _seed_dist_info(tmp_path, "scitex_dev", "0.38.1")
    # Act
    out = resolve_version("scitex-dev", site_packages=tmp_path)
    # Assert
    assert AMBIGUOUS_MARKER in out


def test_ambiguous_output_states_how_many_claim_the_name(tmp_path):
    # Arrange
    _seed_dist_info(tmp_path, "scitex_dev", "0.38.0")
    _seed_dist_info(tmp_path, "scitex_dev", "0.38.1")
    # Act
    out = resolve_version("scitex-dev", site_packages=tmp_path)
    # Assert
    assert "2 dist-info directories" in out


def test_ambiguous_output_still_carries_a_version_string(tmp_path):
    """Withholding the number would trade a wrong answer for a different one.

    Callers parse this; an empty version reads as a BROKEN install rather
    than an AMBIGUOUS one.
    """
    # Arrange
    _seed_dist_info(tmp_path, "scitex_dev", "0.38.0")
    _seed_dist_info(tmp_path, "scitex_dev", "0.38.1")
    # Act
    out = resolve_version("scitex-dev", site_packages=tmp_path)
    # Assert
    assert out.split()[0] != ""


def test_three_dist_infos_are_counted_not_just_flagged(tmp_path):
    # Arrange
    for v in ("0.38.0", "0.38.1", "0.40.4"):
        _seed_dist_info(tmp_path, "scitex_dev", v)
    # Act
    out = resolve_version("scitex-dev", site_packages=tmp_path)
    # Assert
    assert "3 dist-info directories" in out


def test_single_dist_info_is_clean_no_marker(tmp_path):
    """The negative control: this must not flag every install."""
    # Arrange
    _seed_dist_info(tmp_path, "scitex_dev", "0.40.4")
    # Act
    out = resolve_version("scitex-dev", site_packages=tmp_path)
    # Assert
    assert AMBIGUOUS_MARKER not in out


def test_absent_dist_info_is_not_flagged_as_ambiguous(tmp_path):
    """A source checkout / PYTHONPATH import is legitimate, not ambiguous."""
    # Arrange
    (tmp_path / "unrelated").mkdir()
    # Act
    out = resolve_version("scitex-dev", site_packages=tmp_path)
    # Assert
    assert AMBIGUOUS_MARKER not in out


def test_a_different_distributions_dist_infos_do_not_trigger_it(tmp_path):
    """Two dist-infos for ANOTHER package must not implicate this one."""
    # Arrange
    _seed_dist_info(tmp_path, "scitex_cards", "0.17.9")
    _seed_dist_info(tmp_path, "scitex_cards", "0.17.10")
    # Act
    out = resolve_version("scitex-dev", site_packages=tmp_path)
    # Assert
    assert AMBIGUOUS_MARKER not in out


def test_normalized_name_spelling_still_matches(tmp_path):
    """`scitex-dev` vs `scitex_dev` — the on-disk spelling differs."""
    # Arrange
    _seed_dist_info(tmp_path, "scitex_dev", "0.38.0")
    _seed_dist_info(tmp_path, "scitex_dev", "0.38.1")
    # Act
    out = resolve_version("scitex_dev", site_packages=tmp_path)
    # Assert
    assert AMBIGUOUS_MARKER in out


def test_get_version_delegates_to_the_resolver():
    """The rail that was silent must now go through the three-valued path."""
    # Arrange
    from scitex_dev._cli._root import _get_version
    # Act
    out = _get_version()
    # Assert
    assert isinstance(out, str) and out != ""


# EOF
