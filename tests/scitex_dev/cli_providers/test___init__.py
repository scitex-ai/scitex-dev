"""Installed metadata is evidence, not permission to import a command."""

import sys
from dataclasses import FrozenInstanceError

import pytest

from scitex_dev.cli_providers import list_cli_providers


def _dist(root, name, *, explicit=(), consoles=(), files=(), suffix=""):
    info = root / f"{name.replace('-', '_')}-1.0{suffix}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n"
    )
    groups = "[scitex.cli]\n" + "\n".join(f"{n} = {t}" for n, t in explicit)
    groups += "\n[console_scripts]\n" + "\n".join(f"{n} = {t}" for n, t in consoles)
    (info / "entry_points.txt").write_text(groups)
    (info / "RECORD").write_text("".join(f"{file},,\n" for file in files))
    for file in files:
        target = root / file
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text("raise RuntimeError('must not import')\n")
    return info


def test_explicit_unlisted_owner_is_discovered_without_loading(tmp_path):
    # Arrange: loading this real module would execute a sentinel failure.
    (tmp_path / "owned_cli.py").write_text("raise RuntimeError('consumer imported')\n")
    _dist(
        tmp_path,
        "unlisted-owner",
        explicit=[("owned", "owned_cli:main")],
        files=["owned_cli.py"],
    )
    # Act
    (row,) = list_cli_providers(path=[tmp_path])
    # Assert
    assert (
        row.name,
        row.target,
        row.distribution,
        row.status,
        "owned_cli" in sys.modules,
    ) == ("owned", "owned_cli:main", "unlisted-owner", "declared", False)


def test_none_reserves_name_and_suppresses_owner_console_fallback(tmp_path):
    # Arrange
    _dist(
        tmp_path,
        "scitex-owned",
        explicit=[("owned", "none")],
        consoles=[("scitex-owned", "owned:main")],
        files=["owned.py"],
    )
    # Act
    (row,) = list_cli_providers(path=[tmp_path])
    # Assert
    assert (row.name, row.target, row.status, row.source) == (
        "owned",
        None,
        "none",
        "scitex.cli",
    )


@pytest.mark.parametrize(
    "name,target",
    [
        ("bad/name", "owned:main"),
        ("bad name", "owned:main"),
        ("UPPER", "owned:main"),
        ("owned", "owned:main [extra]"),
        ("owned", "foreign:main"),
        ("owned", "../owned:main"),
        ("owned", "owned:main\x01"),
    ],
)
def test_invalid_declarations_never_fall_back(tmp_path, name, target):
    # Arrange
    _dist(
        tmp_path,
        "scitex-owned",
        explicit=[(name, target)],
        consoles=[("scitex-owned", "owned:main")],
        files=["owned.py"],
    )
    # Act
    rows = list_cli_providers(path=[tmp_path])
    # Assert
    assert (len(rows), rows[0].status) == (1, "invalid")


def test_top_level_claim_does_not_prove_nested_module_ownership(tmp_path):
    # Arrange
    info = _dist(tmp_path, "scitex-owned", explicit=[("owned", "foreign.cli:main")])
    (info / "top_level.txt").write_text("foreign\n")
    # Act
    (row,) = list_cli_providers(path=[tmp_path])
    # Assert
    assert row.status == "invalid"


@pytest.mark.parametrize(
    "owner,name",
    [
        ("scitex-owned", "owned"),
        ("figrecipe", "figrecipe"),
        ("socialia", "social"),
        ("crossref-local", "crossref-local"),
        ("openalex-local", "openalex-local"),
        ("newb", "newb"),
    ],
)
def test_legacy_canonical_console_evidence(tmp_path, owner, name):
    # Arrange
    _dist(
        tmp_path,
        owner,
        consoles=[(owner, "owned.cli:main")],
        files=["owned/cli/__init__.py"],
    )
    # Act
    (row,) = list_cli_providers(path=[tmp_path])
    # Assert
    assert (row.name, row.status, row.console_script) == (name, "legacy_unknown", owner)


@pytest.mark.parametrize(
    "owner,console",
    [("pytest", "pytest"), ("uv", "uv"), ("scitex-owned", "alias-only")],
)
def test_other_consoles_are_not_umbrella_eligibility(tmp_path, owner, console):
    # Arrange
    _dist(tmp_path, owner, consoles=[(console, "owned:main")], files=["owned.py"])
    # Act
    (row,) = list_cli_providers(path=[tmp_path])
    # Assert
    assert row.status == "absent"


def test_duplicates_preserved_and_ambiguity_survives_owner_filter(tmp_path):
    # Arrange
    _dist(tmp_path, "first-owner", explicit=[("owned", "none")])
    _dist(
        tmp_path, "second-owner", explicit=[("owned", "owned:main")], files=["owned.py"]
    )
    # Act
    rows = list_cli_providers(path=[tmp_path])
    filtered = list_cli_providers(package="FIRST_owner", path=[tmp_path])
    # Assert
    assert ([row.status for row in rows], [row.status for row in filtered]) == (
        ["ambiguous", "ambiguous"],
        ["ambiguous"],
    )


def test_duplicate_distribution_and_duplicate_entries_are_ambiguous(tmp_path):
    # Arrange
    _dist(tmp_path, "scitex-owned", explicit=[("a", "none"), ("a", "none")])
    _dist(tmp_path, "scitex-owned", explicit=[("b", "none")], suffix="copy")
    # Act
    rows = list_cli_providers(path=[tmp_path])
    # Assert
    assert len(rows) == 3 and all(row.status == "ambiguous" for row in rows)


def test_empty_search_is_not_current_environment(tmp_path):
    # Arrange
    location = tmp_path
    # Act
    rows = list_cli_providers(path=[location])
    # Assert
    assert rows == ()


@pytest.mark.parametrize("layout", ["", "src"])
def test_conventional_owned_editable_source_is_not_imported(tmp_path, layout):
    # Arrange
    import json

    source = tmp_path / "source"
    module = source / layout / "owned" / "cli.py"
    module.parent.mkdir(parents=True)
    module.write_text("raise RuntimeError('must not import editable consumer')\n")
    (source / "pyproject.toml").write_text('[project]\nname="scitex-owned"\n')
    info = _dist(tmp_path, "scitex-owned", explicit=[("owned", "owned.cli:main")])
    (info / "direct_url.json").write_text(
        json.dumps({"url": source.as_uri(), "dir_info": {"editable": True}})
    )
    # Act
    (row,) = list_cli_providers(path=[tmp_path])
    # Assert
    assert row.status == "declared" and "owned.cli" not in sys.modules


@pytest.mark.parametrize("failure", ["foreign-name", "escape", "noneditable", "remote"])
def test_unprovable_editable_refuses(tmp_path, failure):
    # Arrange
    import json

    source = tmp_path / "source"
    source.mkdir()
    module = source / "owned.py"
    module.write_text("raise RuntimeError('must not import')\n")
    (source / "pyproject.toml").write_text(
        '[project]\nname="'
        + ("foreign" if failure == "foreign-name" else "scitex-owned")
        + '"\n'
    )
    _escape_fixture(module, tmp_path, failure)
    info = _dist(tmp_path, "scitex-owned", explicit=[("owned", "owned:main")])
    (info / "direct_url.json").write_text(
        json.dumps(
            {
                "url": (
                    "https://invalid/source" if failure == "remote" else source.as_uri()
                ),
                "dir_info": {"editable": failure != "noneditable"},
            }
        )
    )
    # Act
    (row,) = list_cli_providers(path=[tmp_path])
    # Assert
    assert row.status == "invalid"


def _escape_fixture(module, tmp_path, failure):
    if failure == "escape":
        outside = tmp_path / "outside.py"
        outside.write_text("raise RuntimeError('escaped')\n")
        module.unlink()
        module.symlink_to(outside)


def test_rows_are_frozen(tmp_path):
    # Arrange
    _dist(tmp_path, "owned", explicit=[("owned", "none")])
    (row,) = list_cli_providers(path=[tmp_path])
    # Act
    # Assert
    with pytest.raises(FrozenInstanceError):
        row.status = "changed"


def _editable_shadow_fixture(tmp_path, difference=None):
    import json

    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    (source / "pyproject.toml").write_text('[project]\nname="scitex-owned"\n')
    (source / "src" / "owned.py").write_text("raise RuntimeError('never import')\n")
    installed = _dist(tmp_path, "scitex-owned", explicit=[("owned", "owned:main")])
    (installed / "direct_url.json").write_text(
        json.dumps({"url": source.as_uri(), "dir_info": {"editable": True}})
    )
    shadow = source / "src" / "scitex_owned.egg-info"
    shadow.mkdir()
    (shadow / "PKG-INFO").write_text((installed / "METADATA").read_text())
    (shadow / "entry_points.txt").write_text(
        (installed / "entry_points.txt").read_text()
    )
    if difference == "metadata":
        (shadow / "PKG-INFO").write_text(
            (installed / "METADATA").read_text() + "Summary: different\n"
        )
    if difference == "entrypoints":
        (shadow / "entry_points.txt").write_text("[scitex.cli]\nowned = none\n")
    if difference == "other-root":
        new_root = tmp_path / "other"
        new_root.mkdir()
        shadow.rename(new_root / shadow.name)
        return tmp_path, new_root
    return tmp_path, source / "src"


def test_exact_editable_source_metadata_shadow_is_one_install(tmp_path):
    # Arrange
    paths = _editable_shadow_fixture(tmp_path)
    # Act
    rows = list_cli_providers(path=paths)
    # Assert
    assert [(row.name, row.status) for row in rows] == [("owned", "declared")]


@pytest.mark.parametrize("difference", ["metadata", "entrypoints", "other-root"])
def test_different_source_metadata_remains_ambiguous(tmp_path, difference):
    # Arrange
    paths = _editable_shadow_fixture(tmp_path, difference)
    # Act
    rows = list_cli_providers(path=paths)
    # Assert
    assert [row.status for row in rows] == ["ambiguous", "ambiguous"]


def test_same_physical_metadata_origin_is_not_a_second_install(tmp_path):
    # Arrange
    _dist(tmp_path, "scitex-owned", explicit=[("owned", "none")])
    # Act
    rows = list_cli_providers(path=[tmp_path, tmp_path])
    # Assert
    assert [(row.name, row.status) for row in rows] == [("owned", "none")]


def test_root_public_exports_match_submodule(tmp_path):
    # Arrange
    import scitex_dev
    from scitex_dev.cli_providers import CliProvider

    # Act
    observed = (
        scitex_dev.CliProvider is CliProvider,
        scitex_dev.list_cli_providers is list_cli_providers,
        {"CliProvider", "list_cli_providers"}.issubset(scitex_dev.__all__),
    )
    # Assert
    assert observed == (True, True, True)


def test_discovery_reads_each_metadata_once_and_refreshes_next_call(tmp_path):
    # Arrange
    info = _dist(
        tmp_path,
        "scitex-snapshot",
        explicit=[("snapshot", "snapshot_owned_cli:main")],
        files=["snapshot_owned_cli.py"],
    )
    metadata_path = info / "METADATA"
    opens = []
    enabled = False

    def observe(event, arguments):
        if enabled and event == "open" and arguments[0] == str(metadata_path):
            opens.append(arguments[0])

    sys.addaudithook(observe)

    # Act
    enabled = True
    try:
        first = list_cli_providers(path=[tmp_path])
    finally:
        enabled = False
    first_reads = len(opens)
    metadata_path.write_text(
        "Metadata-Version: 2.1\nName: scitex-snapshot\nVersion: 2.0\n"
    )
    opens.clear()
    enabled = True
    try:
        second = list_cli_providers(path=[tmp_path])
    finally:
        enabled = False
    observed = (
        [(row.name, row.version, row.status) for row in first],
        first_reads,
        [(row.name, row.version, row.status) for row in second],
        len(opens),
        "snapshot_owned_cli" in sys.modules,
    )

    # Assert
    assert observed == (
        [("snapshot", "1.0", "declared")],
        1,
        [("snapshot", "2.0", "declared")],
        1,
        False,
    )
