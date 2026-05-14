"""Test the __version__ drift fixer."""

from __future__ import annotations

from pathlib import Path

from scitex_dev._release.version_fixer import fix_version


def _write_repo(tmp_path: Path, name: str, init_body: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.2.0"\n'
    )
    src = tmp_path / "src" / name.replace("-", "_")
    src.mkdir(parents=True)
    (src / "__init__.py").write_text(init_body)
    return tmp_path


def test_rewrite_replaces_literal_with_dynamic_lookup_rep_action_rewrote(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        '"""docstring."""\n\n__version__ = "0.1.0"\n\nFOO = 1\n',
    )
    rep = fix_version(repo)
    assert rep.action == "rewrote"
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Other code is preserved.


def test_rewrite_replaces_literal_with_dynamic_lookup_rep_old_value_0_1_0(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        '"""docstring."""\n\n__version__ = "0.1.0"\n\nFOO = 1\n',
    )
    rep = fix_version(repo)
    assert rep.old_value == "0.1.0"
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Other code is preserved.


def test_rewrite_replaces_literal_with_dynamic_lookup_importlib_metadata_in_body(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        '"""docstring."""\n\n__version__ = "0.1.0"\n\nFOO = 1\n',
    )
    rep = fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    assert "importlib.metadata" in body
    # Other code is preserved.


def test_rewrite_replaces_literal_with_dynamic_lookup_version_demo_in_body_or__v_demo_in_body(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        '"""docstring."""\n\n__version__ = "0.1.0"\n\nFOO = 1\n',
    )
    rep = fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    assert 'version("demo")' in body or '_v("demo")' in body
    # Other code is preserved.


def test_rewrite_replaces_literal_with_dynamic_lookup_foo_1_in_body(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        '"""docstring."""\n\n__version__ = "0.1.0"\n\nFOO = 1\n',
    )
    rep = fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Other code is preserved.
    assert "FOO = 1" in body


def test_rewrite_replaces_literal_with_dynamic_lookup_docstring_in_body(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        '"""docstring."""\n\n__version__ = "0.1.0"\n\nFOO = 1\n',
    )
    rep = fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Other code is preserved.
    assert "docstring" in body


def test_already_dynamic_is_noop_rep_action_already_dynamic(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        'from importlib.metadata import version as _v\n__version__ = _v("demo")\n',
    )
    rep = fix_version(repo)
    assert rep.action == "already_dynamic"
    # File unchanged.
    body = (repo / "src" / "demo" / "__init__.py").read_text()


def test_already_dynamic_is_noop_body_startswith_from_importlib_metadata(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        'from importlib.metadata import version as _v\n__version__ = _v("demo")\n',
    )
    rep = fix_version(repo)
    # File unchanged.
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    assert body.startswith("from importlib.metadata")


def test_no_literal_inserts_canonical_block_rep_action_inserted(tmp_path):
    """When __version__ is missing entirely, fix_version inserts the
    canonical importlib.metadata block after the docstring + future imports."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(tmp_path, "demo", '"""docstring only."""\n')
    rep = fix_version(repo)
    assert rep.action == "inserted"
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Block was added.
    # Original docstring preserved.
    # Inserted file is syntactically valid + runtime-executable.
    compile(body, "<test>", "exec")
    ns: dict = {}
    exec(body, ns)


def test_no_literal_inserts_canonical_block_importlib_metadata_in_body(tmp_path):
    """When __version__ is missing entirely, fix_version inserts the
    canonical importlib.metadata block after the docstring + future imports."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(tmp_path, "demo", '"""docstring only."""\n')
    rep = fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Block was added.
    assert "importlib.metadata" in body
    # Original docstring preserved.
    # Inserted file is syntactically valid + runtime-executable.
    compile(body, "<test>", "exec")
    ns: dict = {}
    exec(body, ns)


def test_no_literal_inserts_canonical_block_v_demo_in_body(tmp_path):
    """When __version__ is missing entirely, fix_version inserts the
    canonical importlib.metadata block after the docstring + future imports."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(tmp_path, "demo", '"""docstring only."""\n')
    rep = fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Block was added.
    assert '_v("demo")' in body
    # Original docstring preserved.
    # Inserted file is syntactically valid + runtime-executable.
    compile(body, "<test>", "exec")
    ns: dict = {}
    exec(body, ns)


def test_no_literal_inserts_canonical_block_docstring_only_in_body(tmp_path):
    """When __version__ is missing entirely, fix_version inserts the
    canonical importlib.metadata block after the docstring + future imports."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(tmp_path, "demo", '"""docstring only."""\n')
    rep = fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Block was added.
    # Original docstring preserved.
    assert '"""docstring only."""' in body
    # Inserted file is syntactically valid + runtime-executable.
    compile(body, "<test>", "exec")
    ns: dict = {}
    exec(body, ns)


def test_no_literal_inserts_canonical_block_ns___version___0_0_0_local(tmp_path):
    """When __version__ is missing entirely, fix_version inserts the
    canonical importlib.metadata block after the docstring + future imports."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(tmp_path, "demo", '"""docstring only."""\n')
    rep = fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Block was added.
    # Original docstring preserved.
    # Inserted file is syntactically valid + runtime-executable.
    compile(body, "<test>", "exec")
    ns: dict = {}
    exec(body, ns)
    assert ns["__version__"] == "0.0.0+local"


def test_no_literal_with_future_import_rep_action_inserted(tmp_path):
    """Insertion goes AFTER `from __future__` imports (PEP 236 compliance)."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        '"""docstring."""\nfrom __future__ import annotations\n\nimport os\n',
    )
    rep = fix_version(repo)
    assert rep.action == "inserted"
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Future import precedes the block (Python requires this).
    future_pos = body.index("from __future__")
    block_pos = body.index("importlib.metadata")
    # Original `import os` still present.


def test_no_literal_with_future_import_future_pos_block_pos(tmp_path):
    """Insertion goes AFTER `from __future__` imports (PEP 236 compliance)."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        '"""docstring."""\nfrom __future__ import annotations\n\nimport os\n',
    )
    rep = fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Future import precedes the block (Python requires this).
    future_pos = body.index("from __future__")
    block_pos = body.index("importlib.metadata")
    assert future_pos < block_pos, "future import must come before version block"
    # Original `import os` still present.


def test_no_literal_with_future_import_import_os_in_body(tmp_path):
    """Insertion goes AFTER `from __future__` imports (PEP 236 compliance)."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "demo",
        '"""docstring."""\nfrom __future__ import annotations\n\nimport os\n',
    )
    rep = fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Future import precedes the block (Python requires this).
    future_pos = body.index("from __future__")
    block_pos = body.index("importlib.metadata")
    # Original `import os` still present.
    assert "import os" in body


def test_dry_run_does_not_write_rep_action_rewrote(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(tmp_path, "demo", '__version__ = "0.1.0"\n')
    rep = fix_version(repo, dry_run=True)
    assert rep.action == "rewrote"
    body = (repo / "src" / "demo" / "__init__.py").read_text()


def test_dry_run_does_not_write_body___version___0_1_0_n(tmp_path):
    # Arrange
    # Act
    # Assert
    repo = _write_repo(tmp_path, "demo", '__version__ = "0.1.0"\n')
    rep = fix_version(repo, dry_run=True)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    assert body == '__version__ = "0.1.0"\n'


def test_fixed_init_imports_cleanly_version___in_ns(tmp_path):
    """The rewritten file must be syntactically valid + executable."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(tmp_path, "demo", '__version__ = "0.1.0"\n')
    fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Compile; raises SyntaxError if broken.
    compile(body, "<test>", "exec")
    # Run in an isolated namespace; no NameError on _v cleanup etc.
    ns: dict = {}
    exec(body, ns)
    assert "__version__" in ns
    # Falls back to "0.0.0+local" because demo isn't installed.


def test_fixed_init_imports_cleanly_ns___version___0_0_0_local(tmp_path):
    """The rewritten file must be syntactically valid + executable."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(tmp_path, "demo", '__version__ = "0.1.0"\n')
    fix_version(repo)
    body = (repo / "src" / "demo" / "__init__.py").read_text()
    # Compile; raises SyntaxError if broken.
    compile(body, "<test>", "exec")
    # Run in an isolated namespace; no NameError on _v cleanup etc.
    ns: dict = {}
    exec(body, ns)
    # Falls back to "0.0.0+local" because demo isn't installed.
    assert ns["__version__"] == "0.0.0+local"


def test_kebab_name_uses_dash_in_metadata(tmp_path):
    """The dist-name in version() must be the pip name (kebab-case)."""
    # Arrange
    # Act
    # Assert
    repo = _write_repo(
        tmp_path,
        "scitex-foo",
        '__version__ = "0.1.0"\n',
    )
    fix_version(repo)
    body = (repo / "src" / "scitex_foo" / "__init__.py").read_text()
    assert '"scitex-foo"' in body
