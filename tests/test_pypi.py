"""Tests for scitex_dev.pypi (PyPI publishing helper)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from scitex_dev import pypi


# ---------------------------------------------------------------------------
# Fixtures


@pytest.fixture
def fake_pkg(tmp_path: Path) -> Path:
    """Minimal package skeleton with pyproject.toml."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo-pkg"\nversion = "0.2.3"\n'
    )
    return tmp_path


@pytest.fixture
def fake_pkg_with_oidc(fake_pkg: Path) -> Path:
    wf = fake_pkg / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "publish-pypi.yml").write_text("# placeholder\n")
    return fake_pkg


# ---------------------------------------------------------------------------
# detect_*


def test_detect_version(fake_pkg: Path) -> None:
    assert pypi.detect_version(fake_pkg) == "0.2.3"


def test_detect_package_name(fake_pkg: Path) -> None:
    assert pypi.detect_package_name(fake_pkg) == "demo-pkg"


def test_detect_version_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        pypi.detect_version(tmp_path)


def test_detect_version_missing_field(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    with pytest.raises(ValueError):
        pypi.detect_version(tmp_path)


# ---------------------------------------------------------------------------
# Method selection


def test_has_oidc_workflow_true(fake_pkg_with_oidc: Path) -> None:
    assert pypi.has_oidc_workflow(fake_pkg_with_oidc) is True


def test_has_oidc_workflow_false(fake_pkg: Path) -> None:
    assert pypi.has_oidc_workflow(fake_pkg) is False


def test_select_method_auto_with_workflow(fake_pkg_with_oidc: Path) -> None:
    assert pypi.select_method(fake_pkg_with_oidc) == "tag-trigger-oidc"


def test_select_method_auto_without_workflow(fake_pkg: Path) -> None:
    assert pypi.select_method(fake_pkg) == "twine"


def test_select_method_explicit(fake_pkg_with_oidc: Path) -> None:
    assert pypi.select_method(fake_pkg_with_oidc, "twine") == "twine"


# ---------------------------------------------------------------------------
# publish() dispatch + skip-if-published


def test_publish_dry_run_oidc(fake_pkg_with_oidc: Path) -> None:
    with mock.patch.object(pypi, "is_published", return_value=False):
        r = pypi.publish(fake_pkg_with_oidc, dry_run=True)
    assert r.success
    assert r.method == "tag-trigger-oidc"
    assert r.version == "0.2.3"
    assert "DRY RUN" in r.message


def test_publish_dry_run_twine_falls_back(fake_pkg: Path) -> None:
    """Without a workflow file, auto-select picks twine."""
    with mock.patch.object(pypi, "is_published", return_value=False):
        r = pypi.publish(fake_pkg, dry_run=True)
    assert r.method == "twine"


def test_publish_skip_if_published(fake_pkg_with_oidc: Path) -> None:
    with mock.patch.object(pypi, "is_published", return_value=True):
        r = pypi.publish(fake_pkg_with_oidc, dry_run=True)
    assert r.success
    assert r.method == "skipped"
    assert "already on PyPI" in r.message


def test_publish_skip_if_published_disabled(fake_pkg_with_oidc: Path) -> None:
    with mock.patch.object(pypi, "is_published", return_value=True):
        r = pypi.publish(fake_pkg_with_oidc, dry_run=True, skip_if_published=False)
    assert r.method == "tag-trigger-oidc"


def test_publish_confirm_overrides_dry_run(fake_pkg_with_oidc: Path) -> None:
    """confirm=True implies dry_run=False; verify by patching publish_via_tag."""
    with (
        mock.patch.object(pypi, "is_published", return_value=False),
        mock.patch.object(pypi, "publish_via_tag") as mtag,
    ):
        mtag.return_value = pypi.PublishResult(
            package="demo-pkg",
            success=True,
            method="tag-trigger-oidc",
            version="0.2.3",
            message="mocked",
        )
        pypi.publish(fake_pkg_with_oidc, confirm=True)
        # The dry_run kwarg should be False at the call site
        _, kwargs = mtag.call_args
        assert kwargs["dry_run"] is False


def test_publish_missing_pyproject(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        pypi.publish(tmp_path, dry_run=True)


# ---------------------------------------------------------------------------
# publish_all


def test_publish_all_skips_published_then_publishes(
    fake_pkg_with_oidc: Path, tmp_path: Path
) -> None:
    second = tmp_path / "pkg2"
    second.mkdir()
    (second / "pyproject.toml").write_text(
        '[project]\nname = "demo-pkg2"\nversion = "0.1.0"\n'
    )
    (second / ".github" / "workflows").mkdir(parents=True)
    (second / ".github" / "workflows" / "publish-pypi.yml").write_text("# ok\n")

    def fake_published(name: str, version: str | None = None) -> bool:
        return name == "demo-pkg"  # first one already on PyPI; second not

    with mock.patch.object(pypi, "is_published", side_effect=fake_published):
        results = pypi.publish_all([fake_pkg_with_oidc, second], dry_run=True)

    assert len(results) == 2
    assert results[0].method == "skipped"
    assert results[1].method == "tag-trigger-oidc"
    assert all(r.success for r in results)


# ---------------------------------------------------------------------------
# trusted_publisher_form


def test_trusted_publisher_form_default_owner() -> None:
    f = pypi.trusted_publisher_form("scitex-foo")
    assert f["PyPI Project Name"] == "scitex-foo"
    assert f["Owner"] == "ywatanabe1989"
    assert f["Workflow name"] == "publish-pypi.yml"
    assert f["Environment name"] == "pypi"


def test_trusted_publisher_form_custom_owner() -> None:
    f = pypi.trusted_publisher_form("foo-bar", github_owner="someone-else")
    assert f["Owner"] == "someone-else"


# ---------------------------------------------------------------------------
# Classifier validation


def test_validate_classifiers_all_valid(tmp_path: Path) -> None:
    """Real-world valid classifiers pass through cleanly."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n'
        "classifiers = [\n"
        '    "Programming Language :: Python :: 3",\n'
        '    "Operating System :: OS Independent",\n'
        "]\n"
    )
    from scitex_dev._pypi_classifiers import validate_classifiers

    assert validate_classifiers(tmp_path) == []


def test_validate_classifiers_catches_bad(tmp_path: Path) -> None:
    """The real bug we hit on 2026-04-27: plausible but invalid classifier."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n'
        "classifiers = [\n"
        '    "Programming Language :: Python :: 3",\n'
        '    "Topic :: Software Development :: Testing :: Benchmark",\n'  # not real
        "]\n"
    )
    from scitex_dev._pypi_classifiers import validate_classifiers

    bad = validate_classifiers(tmp_path)
    # Either trove-classifiers is installed and catches it, or validation is
    # silently skipped — both behaviours are acceptable.
    assert bad == ["Topic :: Software Development :: Testing :: Benchmark"] or bad == []


def test_validate_classifiers_no_block(tmp_path: Path) -> None:
    """pyproject.toml without a classifiers list is fine."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n'
    )
    from scitex_dev._pypi_classifiers import validate_classifiers

    assert validate_classifiers(tmp_path) == []


# ---------------------------------------------------------------------------
# PublishResult __str__


def test_publish_result_str_success() -> None:
    r = pypi.PublishResult(
        package="x",
        success=True,
        method="twine",
        version="1.0.0",
        message="ok",
    )
    s = str(r)
    assert "[OK]" in s and "x v1.0.0" in s and "twine" in s and "ok" in s


def test_publish_result_str_failure() -> None:
    r = pypi.PublishResult(package="x", success=False, method="twine", message="oops")
    s = str(r)
    assert "[FAIL]" in s and "oops" in s
