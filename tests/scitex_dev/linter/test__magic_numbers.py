"""Tests for STX-S008 — hard-coded analysis parameters in scripts.

Real source samples linted through the real engine (``lint_source``) with a
real ``LinterConfig``; no mocks. Each sample is a realistic research-script
idiom; the rule must flag analysis parameters and leave harmless literals
(indices, shapes, arithmetic, plotting style, infrastructure) alone.
"""

from __future__ import annotations

import pytest
from scitex_dev.linter.checker import lint_source
from scitex_dev.linter.config import LinterConfig, load_config

_HEADER = "import numpy as np\nimport scitex as stx\nfrom scipy import signal\n\n\n"
_SESSION = (
    "@stx.session\n"
    "def main(CONFIG=stx.session.INJECTED, plt=stx.session.INJECTED,\n"
    "         COLORS=stx.session.INJECTED, rngg=stx.session.INJECTED,\n"
    "         logger=stx.session.INJECTED):\n"
    "{body}\n"
    "    return 0\n"
    "\n\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)


def _session_script(body: str) -> str:
    indented = "\n".join("    " + line for line in body.splitlines())
    return _HEADER + _SESSION.format(body=indented)


def _s008_lines(src: str, filepath: str = "analysis.py", config=None) -> list:
    issues = lint_source(src, filepath=filepath, config=config or LinterConfig())
    return [i.line for i in issues if i.rule.id == "STX-S008"]


# -- analysis parameters that must be flagged --------------------------------

_FLAGGED = {
    "local_assignment_in_main": "window_size = 256",
    "annotated_local": "alpha_level: float = 0.05",
    "negative_literal": "lag_ms = -150",
    "list_of_frequencies": "freqs = [4, 8, 13, 30]",
    "dict_of_bands": 'bands = {"theta": (4, 8), "alpha": (8, 13)}',
    "keyword_argument": "f, pxx = signal.welch(np.ones(8), fs=512)",
    "bootstrap_count_keyword": "res = stx.stats.bootstrap(np.ones(8), n_resamples=5000)",
    "float_threshold_comparison": "mask = np.ones(8) > 3.5",
    "pvalue_threshold": "sig = CONFIG.P < 0.01",
    "seed_keyword_zero": "rng = np.random.default_rng(seed=0)",
    "seed_positional": "np.random.seed(1234)",
    "default_rng_positional": "rng = np.random.default_rng(42)",
    "seed_name_trivial": "SEED = 0",
    "half_threshold_keyword": "out = stx.stats.detect(np.ones(8), threshold=0.5)",
    "percent_keyword": "out = stx.stats.trim(np.ones(8), n_iter=100)",
}


@pytest.mark.parametrize("body", _FLAGGED.values(), ids=list(_FLAGGED))
def test_analysis_parameter_in_session_main_is_flagged(body):
    # Arrange
    src = _session_script(body)
    # Act
    lines = _s008_lines(src)
    # Assert
    assert lines == [_HEADER.count("\n") + 5]


def test_helper_signature_default_is_flagged():
    # Arrange
    src = _HEADER + "def bandpass(x, low=1.5, high=30.0, order=4):\n    return x\n"
    # Act
    lines = _s008_lines(src)
    # Assert
    assert lines == [6]


def test_session_main_cli_default_is_flagged():
    # Arrange
    src = _HEADER + _SESSION.replace(
        "def main(CONFIG", "def main(threshold: float = 0.7, CONFIG"
    ).format(body="    pass")
    # Act
    lines = _s008_lines(src)
    # Assert
    assert lines == [7]


def test_module_scope_upper_constant_is_flagged():
    # Arrange
    src = _HEADER + "N_BOOTSTRAP = 1_000\n"
    # Act
    lines = _s008_lines(src)
    # Assert
    assert lines == [6]


def test_several_parameters_on_one_line_are_one_finding():
    # Arrange
    src = _session_script("f, pxx = signal.welch(np.ones(8), fs=512, nperseg=128)")
    issues = lint_source(src, filepath="analysis.py", config=LinterConfig())
    # Act
    s008 = [i for i in issues if i.rule.id == "STX-S008"]
    # Assert
    assert [i.rule.message.split("`")[1] for i in s008] == ["fs=512, nperseg=128"]


def test_finding_message_names_value_and_config():
    # Arrange
    src = _session_script("window_size = 256")
    issues = lint_source(src, filepath="analysis.py", config=LinterConfig())
    # Act
    msg = next(i.rule.message for i in issues if i.rule.id == "STX-S008")
    # Assert
    assert msg == (
        "Hard-coded parameter `window_size = 256` — move it to config/*.yaml "
        "and read it from CONFIG"
    )


# -- harmless literals that must NOT be flagged ------------------------------

_HARMLESS = {
    "trivial_numbers": "a = 0\nb = 1\nc = -1\nd = 2.0",
    "halving_arithmetic": "half = len(CONFIG.X) // 2",
    "indexing": "last = CONFIG.X[-1]\nfirst = CONFIG.X[:, 3]",
    "range_len": "for i in range(len(CONFIG.X)):\n    pass",
    "unit_conversion": "ms = CONFIG.T * 1000",
    "axis_keyword": "m = np.mean(CONFIG.X, axis=0)\ns = np.std(CONFIG.X, ddof=1)",
    "shape_positional": "y = np.zeros((10, 3))",
    "rounding": "r = round(CONFIG.X, 3)\nq = np.round(CONFIG.X, decimals=3)",
    "string_format": 's = f"{CONFIG.X:.3f}"',
    "plotting_style": (
        "fig, axes = plt.subplots(2, 3)\n"
        "axes[0, 0].plot(CONFIG.X, alpha=0.3, linewidth=0.8)\n"
        "axes[0, 1].set_title('t', fontsize=7, pad=3)"
    ),
    "diagram_geometry": "CONFIG.S.add_box('a', 'A', x_mm=40, y_mm=50, width_mm=30)",
    "infrastructure_keywords": (
        "txt = stx.io.dumps(CONFIG, indent=4)\n"
        "stx.io.save(CONFIG, 'x.jpg', dpi=300)\n"
        "out = stx.sh.run('ls', timeout=30)"
    ),
    "int_size_guard": "if len(CONFIG.X) > 10:\n    pass",
    "int_status_code": "ok = CONFIG.STATUS == 200",
    "numerical_tolerance": "same = abs(CONFIG.A - CONFIG.B) < 1e-12",
    "compression_keyword": "stx.io.save(CONFIG, 'x.h5', compression_opts=4)",
    "version_comparison": "import sys\nold = sys.version_info < (3, 10)",
    "value_from_config": "thr = CONFIG.ANALYSIS.THRESHOLD",
    "config_get_fallback": "thr = CONFIG.get('THRESHOLD', 0.5)",
    "dict_keys_are_codes": 'labels = {4: "rest", 7: "task"}',
    "private_and_version_names": "_CACHE = 512\nVERSION_INFO = (0, 1, 3)",
    "strings_and_bools": 'name = "sub-01"\nflag = True',
    "allow_comment": "window = 256  # stx-allow: STX-S008",
}


@pytest.mark.parametrize("body", _HARMLESS.values(), ids=list(_HARMLESS))
def test_harmless_literal_is_not_flagged(body):
    # Arrange
    src = _session_script(body)
    # Act
    lines = _s008_lines(src)
    # Assert
    assert lines == []


def test_enum_member_values_are_not_flagged():
    # Arrange
    src = _HEADER + "import enum\n\n\nclass Stage(enum.IntEnum):\n    WAKE = 5\n"
    # Act
    lines = _s008_lines(src)
    # Assert
    assert lines == []


def test_test_file_is_not_flagged():
    # Arrange
    src = "def test_window_size_default():\n    window = 256\n    assert window\n"
    # Act
    lines = _s008_lines(src, filepath="tests/test_analysis.py")
    # Assert
    assert lines == []


def test_library_module_without_session_is_not_flagged():
    # Arrange
    src = "WINDOW = 256\n"
    # Act
    lines = _s008_lines(src, filepath="src/pkg/_core.py")
    # Assert
    assert lines == []


# -- research scope: scripts/ is where research analysis code lives ----------


def test_research_project_script_dir_file_is_flagged():
    # Arrange
    config = LinterConfig(project_types=["research"])
    src = "window = 256\n"
    # Act
    lines = _s008_lines(src, filepath="scripts/analysis/01_psd.py", config=config)
    # Assert
    assert lines == [1]


def test_non_research_project_script_dir_file_is_not_flagged():
    # Arrange
    src = "window = 256\n"
    # Act
    lines = _s008_lines(src, filepath="scripts/release/bump.py")
    # Assert
    assert lines == []


def test_session_script_under_script_dir_is_flagged():
    # Arrange
    src = _session_script("window = 256")
    # Act
    lines = _s008_lines(src, filepath="scripts/analysis/01_psd.py")
    # Assert
    assert lines == [_HEADER.count("\n") + 5]


# -- severity: info by default, warning under `project-type: research` -------


def _severity_in(tmp_path, yaml_body: str) -> str:
    (tmp_path / ".scitex" / "dev").mkdir(parents=True)
    (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(yaml_body)
    script = tmp_path / "scripts" / "analysis" / "01_psd.py"
    cfg = load_config(start_path=str(tmp_path))
    issues = lint_source("window = 256\n", filepath=str(script), config=cfg)
    return next(i.rule.severity for i in issues if i.rule.id == "STX-S008")


def test_research_project_promotes_s008_to_warning(tmp_path):
    # Arrange
    yaml_body = "project-type: research\n"
    # Act
    severity = _severity_in(tmp_path, yaml_body)
    # Assert
    assert severity == "warning"


def test_session_script_outside_research_keeps_s008_info():
    # Arrange
    src = _session_script("window = 256")
    # Act
    issues = lint_source(src, filepath="analysis.py", config=LinterConfig())
    # Assert
    assert {i.rule.severity for i in issues if i.rule.id == "STX-S008"} == {"info"}
