"""PS126 checks dependency lower bounds rather than version-string prefixes."""
from dataclasses import dataclass

import pytest

from scitex_dev._cli.audit._project._check_sphinx_html import check_sphinx_html


@dataclass
class _Finding:
    rule: str
    where: str
    detail: str


_DEFAULTS = {
    "sphinx": "sphinx>=7.0",
    "sphinx-rtd-theme": "sphinx-rtd-theme>=2.0",
    "myst-parser": "myst-parser>=2.0",
    "sphinx-copybutton": "sphinx-copybutton>=0.5",
    "sphinx-autodoc-typehints": "sphinx-autodoc-typehints>=1.25",
}


@pytest.mark.parametrize("name,requirement,refused", [
    ("myst-parser", "myst-parser>=3.0", False),
    ("sphinx", "sphinx>=7.2.5", False),
    ("sphinx", "sphinx>=8.0,<10", False),
    ("sphinx", "sphinx==8.1.3", False),
    ("sphinx", "sphinx==8.*", False),
    ("sphinx", "sphinx==7.*", True),
    ("sphinx", "sphinx==7.0.0", False),
    ("sphinx", "sphinx~=7.2.5", False),
    ("sphinx", "sphinx>7.0", False),
    ("sphinx", "Sphinx >= 7.2.5 # include-read support", False),
    ("sphinx-autodoc-typehints", "sphinx-autodoc-typehints>=2.0", False),
    ("sphinx-autodoc-typehints", "sphinx-autodoc-typehints>=1.0", True),
    ("sphinx-copybutton", "sphinx-copybutton>=0.4", True),
    ("myst-parser", "myst-parser>=1.9", True),
    ("sphinx", "sphinx", True),
    ("sphinx", "sphinx<8", True),
    ("sphinx", "sphinx!=6.0", True),
    ("sphinx", "sphinx==6.*", True),
    ("sphinx", "sphinx~=6.9", True),
    ("sphinx", "sphinx>=7.0rc1", True),
    ("sphinx", "sphinx>=8; platform_system == 'Windows'", True),
    ("sphinx", "sphinx @ https://example.invalid/sphinx.whl", True),
    ("sphinx", "# sphinx>=8", True),
    ("sphinx", "sphinx>=not-a-version", True),
    ("sphinx", "", True),
])
def test_ps126_requires_a_proven_unconditional_floor(tmp_path, name, requirement, refused):
    # Arrange
    docs = tmp_path / "docs/sphinx"
    docs.mkdir(parents=True)
    (docs / "conf.py").write_text("project = 'floor-contract'\n")
    declarations = {**_DEFAULTS, name: requirement}
    (docs / "requirements.txt").write_text("\n".join(declarations.values()) + "\n")
    findings = []
    # Act
    check_sphinx_html(tmp_path, _Finding, findings)
    floor_refused = any(item.rule == "PS-126" for item in findings)
    # Assert
    assert floor_refused is refused
