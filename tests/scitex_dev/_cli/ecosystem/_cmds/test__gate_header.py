"""Regeneration must leave handwritten tests executable, not merely present."""

from __future__ import annotations

import os
import subprocess
import sys

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli.ecosystem._cmds._gate_header import (
    read_header_imports,
    render_header_imports,
)
from scitex_dev._cli.ecosystem._cmds._gate_sentinel import (
    BEGIN_SENTINEL,
    END_SENTINEL,
    split_at_sentinel,
)
from scitex_dev._cli.ecosystem._cmds._install_cross_package_gate import register

PREFIX = '''"""Owned test header."""
from __future__ import (
    annotations,
)
import importlib as loader
import pytest
from pathlib import (
    Path as OwnedPath,
)
import tomllib as toml
'''
TAIL = END_SENTINEL + """

class AnnotationProbe:
    value: NotImportedType

def test_handwritten_header_dependencies():
    assert OwnedPath(__file__).is_file()
    assert toml.loads('value = 42')['value'] == 42
    assert loader.import_module('pathlib').Path is OwnedPath
    assert AnnotationProbe.__annotations__ == {'value': 'NotImportedType'}
"""


def _fixture(tmp_path, header=PREFIX, tail=TAIL):
    repo = tmp_path / "leaf"
    src = repo / "src/scitex_header_demo"
    src.mkdir(parents=True)
    (repo / "pyproject.toml").write_text('[project]\nname="scitex-header-demo"\n')
    (src / "__init__.py").write_text("import scitex_sdk.app\n")
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    gate = repo / "tests/integration/test_cross_package_imports.py"
    gate.parent.mkdir(parents=True)
    gate.write_text(header + BEGIN_SENTINEL + "\nCROSS_PACKAGE_IMPORTS = []\n" + tail)
    return repo, gate


def _install(repo, *extra):
    group = click.Group()
    register(group)
    return CliRunner().invoke(
        group,
        [
            "install-cross-package-gate",
            "scitex-header-demo",
            "--path",
            str(repo),
            "--force",
            *extra,
        ],
    )


def test_normal_force_twice_preserves_imports_and_executes_actual_gate(tmp_path):
    # Arrange
    repo, gate = _fixture(tmp_path)
    observations = []
    # Act
    for _ in range(2):
        result = _install(repo)
        source = gate.read_text()
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-m",
                "pytest",
                str(gate),
                "--confcutdir",
                str(repo),
                "-o",
                "addopts=",
                "-q",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
            env={
                key: os.environ[key]
                for key in ("HOME", "PATH", "LANG")
                if key in os.environ
            },
        )
        observations.append(
            (
                result.exit_code,
                source.endswith(TAIL),
                all(segment in source for segment in read_header_imports(PREFIX)),
                "import importlib\n" in source,
                source.count("import pytest\n"),
                source.index("from __future__") < source.index("import importlib"),
                completed.returncode,
                "1 passed" in completed.stdout,
            )
        )
    # Assert
    assert observations == [(0, True, True, True, 1, True, 0, True)] * 2, (
        result.output,
        completed.stdout,
        completed.stderr,
    )


@pytest.mark.parametrize(
    "header",
    [
        "import pathlib\ncustom_state = 1\n",
        "from pathlib import (\n",
        "import pathlib\nfrom __future__ import annotations\n",
        "if True:\n    import pathlib\n",
    ],
)
def test_unsupported_header_refuses_without_writing(tmp_path, header):
    # Arrange
    repo, gate = _fixture(tmp_path, header)
    before = gate.read_bytes()
    # Act
    result = _install(repo)
    # Assert
    assert (
        result.exit_code != 0,
        gate.read_bytes() == before,
        (gate.parent / "__init__.py").exists(),
    ) == (True, True, False)


@pytest.mark.parametrize(
    "content",
    [
        PREFIX + END_SENTINEL + "\n",
        PREFIX + BEGIN_SENTINEL + "\n",
        PREFIX + BEGIN_SENTINEL + "\n" + TAIL + END_SENTINEL + "\n",
        PREFIX + END_SENTINEL + "\n" + BEGIN_SENTINEL + "\n",
        PREFIX + "# no marker pair\n",
    ],
)
def test_ambiguous_or_missing_markers_refuse_without_writing(tmp_path, content):
    # Arrange
    repo, gate = _fixture(tmp_path)
    gate.write_text(content)
    before = gate.read_bytes()
    # Act
    result = _install(repo)
    # Assert
    assert (
        result.exit_code != 0,
        gate.read_bytes() == before,
        (gate.parent / "__init__.py").exists(),
    ) == (True, True, False)


def test_quoted_marker_text_is_not_a_boundary():
    # Arrange
    prefix = '"""\n' + END_SENTINEL + '\n"""\nimport pathlib\n'
    # Act
    split = split_at_sentinel(
        prefix + BEGIN_SENTINEL + "\nCROSS_PACKAGE_IMPORTS = []\n" + TAIL
    )
    # Assert
    assert (split.header_imports, split.tail) == (("import pathlib",), TAIL)


def test_rendered_alias_does_not_replace_required_baseline_binding():
    # Arrange
    imports = ("import pytest as check", "import importlib as loader")
    # Act
    source = render_header_imports(imports)
    # Assert
    assert all(
        part in source
        for part in (
            "import pytest as check\n",
            "import importlib as loader\n",
            "import pytest\n",
            "import importlib\n",
        )
    )


def test_force_preserves_actual_crlf_tail_bytes(tmp_path):
    # Arrange
    repo, gate = _fixture(tmp_path)
    gate.write_bytes(gate.read_bytes().replace(b"\n", b"\r\n"))
    tail = TAIL.replace("\n", "\r\n").encode()
    # Act
    result = _install(repo)
    # Assert
    assert (result.exit_code, gate.read_bytes().endswith(tail)) == (
        0,
        True,
    ), result.output
