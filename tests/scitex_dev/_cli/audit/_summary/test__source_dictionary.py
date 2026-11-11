"""Run real source controls with one installed metadata origin.

Editable CI also exposes the checkout's egg-info and the image's baked wheel.
Those distinct origins correctly remain ambiguous. The positive source controls
need a single real metadata origin, without deleting any installed metadata or
weakening production ownership checks.
"""

import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

_BOOTSTRAP = """
import importlib.util
import sys
from pathlib import Path

root, site, cases, gate = map(Path, sys.argv[1:])
# -I -S retains the interpreter's standard library, but loads no baked site or
# editable .pth. This is the actual complete declared dependency installation.
sys.path.append(str(site))
spec = importlib.util.spec_from_file_location(
    'scitex_dev', root / 'src/scitex_dev/__init__.py',
    submodule_search_locations=[str(root / 'src/scitex_dev')],
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
from importlib.metadata import distributions
origins = {
    str(item._path.resolve()) for item in distributions()
    if item.metadata['Name'] == 'scitex-dev'
}
if len(origins) != 1:
    raise RuntimeError(f'Controls require one actual Dev metadata origin: {origins}')
import pytest
raise SystemExit(pytest.main([str(cases), str(gate), '-q']))
"""


def test_actual_source_controls_preserve_owner_boundaries():
    # Arrange
    cases = Path(__file__).with_name("_source_dictionary_cases.py")
    root = cases.resolve().parents[5]
    site = distribution("scitex-sdk")._path.resolve().parent
    command = [
        sys.executable,
        "-I",
        "-S",
        "-c",
        _BOOTSTRAP,
        str(root),
        str(site),
        str(cases),
        str(root / "tests/develop/test_audit.py"),
    ]
    # Act
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    # Assert
    assert (result.returncode, "13 passed" in result.stdout) == (0, True), (
        result.stdout + result.stderr
    )
