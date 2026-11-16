"""Tests for STX-RIO001-003 (raw pathlib / shutil file I/O) and the deferred
STX-PA002 (bare ``open()``) emission.

Hands-on finding (2026-11): an agent wrote research results via
``pathlib.Path.write_text`` and raw ``open()``; no rule fired and clew
recorded none of those files. These tests pin that every such call in a
research script is now REQUESTED, and that ordinary library / test code is
left alone.

They run the real ``lint_source`` pipeline. ``observe_lint`` records what
the engine requests before the ``requires="scitex"`` availability filter;
the emitted count is checked against the real ``detect()`` result, never a
replaced one.
"""

from scitex_dev.linter._packages import detect
from scitex_dev.linter._rules import ALL_RULES
from scitex_dev.linter.config import LinterConfig

_SESSION = (
    "import scitex as stx\n"
    "{imports}"
    "\n"
    "\n"
    "{helpers}"
    "@stx.session\n"
    "def main(\n"
    "    CONFIG=stx.session.INJECTED,\n"
    "    COLORS=stx.session.INJECTED,\n"
    "    logger=stx.session.INJECTED,\n"
    "    plt=stx.session.INJECTED,\n"
    "    rngg=stx.session.INJECTED,\n"
    "):\n"
    "{body}"
    "    return 0\n"
    "\n"
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)

_RAW_IDS = {"STX-RIO001", "STX-RIO002", "STX-RIO003", "STX-PA002"}


def _session(body="", imports="from pathlib import Path\n", helpers=""):
    return _SESSION.format(imports=imports, body=body, helpers=helpers)


def _raw(observe_lint, src, filepath="examples/run_analysis.py", config=None):
    """(requested raw-io ids, emitted raw-io ids) for *src*."""
    requests, issues = observe_lint(
        src, filepath=filepath, config=config or LinterConfig()
    )
    req = sorted(r.id for r in requests if r.id in _RAW_IDS)
    emitted = sorted(i.rule.id for i in issues if i.rule.id in _RAW_IDS)
    return req, emitted


def _scitex() -> int:
    return int(detect()["scitex"])


# --------------------------------------------------------------------------- #
# Registration                                                                #
# --------------------------------------------------------------------------- #


def test_raw_io_rules_registered_in_engine():
    # Arrange
    ids = ("STX-RIO001", "STX-RIO002", "STX-RIO003")
    # Act
    present = [rid in ALL_RULES for rid in ids]
    # Assert
    assert present == [True, True, True]


def test_raw_io_rules_are_io_category_so_research_promotes_them():
    # Arrange
    ids = ("STX-RIO001", "STX-RIO002", "STX-RIO003")
    # Act
    cats = {ALL_RULES[rid].category for rid in ids}
    # Assert
    assert cats == {"io"}


def test_raw_io_suggestions_name_stx_io_fix():
    # Arrange
    rules = [ALL_RULES[r] for r in ("STX-RIO001", "STX-RIO002", "STX-RIO003")]
    # Act
    mentions = ["stx.io." in r.suggestion for r in rules]
    # Assert
    assert mentions == [True, True, True]


# --------------------------------------------------------------------------- #
# Positive — inside an @stx.session module                                    #
# --------------------------------------------------------------------------- #


def test_path_write_text_in_session_requests_rio001(observe_lint):
    # Arrange
    src = _session('    Path("out/results.txt").write_text("hello")\n')
    # Act
    req, emitted = _raw(observe_lint, src)
    # Assert
    assert (req, len(emitted)) == (["STX-RIO001"], _scitex())


def test_path_write_bytes_on_variable_requests_rio001(observe_lint):
    # Arrange
    src = _session('    p = Path("out/b.bin")\n    p.write_bytes(b"x")\n')
    # Act
    req, _ = _raw(observe_lint, src)
    # Assert
    assert req == ["STX-RIO001"]


def test_path_read_text_in_session_requests_rio002(observe_lint):
    # Arrange
    src = _session('    data = Path("data/in.csv").read_text()\n')
    # Act
    req, emitted = _raw(observe_lint, src)
    # Assert
    assert (req, len(emitted)) == (["STX-RIO002"], _scitex())


def test_path_read_bytes_in_session_requests_rio002(observe_lint):
    # Arrange
    src = _session('    raw = Path("in.bin").read_bytes()\n')
    # Act
    req, _ = _raw(observe_lint, src)
    # Assert
    assert req == ["STX-RIO002"]


def test_path_open_write_mode_requests_rio001(observe_lint):
    # Arrange
    src = _session(
        '    with Path("out/r.json").open("w") as f:\n        f.write("{}")\n'
    )
    # Act
    req, _ = _raw(observe_lint, src)
    # Assert
    assert req == ["STX-RIO001"]


def test_path_join_open_default_mode_requests_rio002(observe_lint):
    # Arrange — `(base / "x").open()` reads.
    src = _session(
        '    base = Path("data")\n'
        '    with (base / "in.txt").open() as f:\n'
        "        f.read()\n"
    )
    # Act
    req, _ = _raw(observe_lint, src)
    # Assert
    assert req == ["STX-RIO002"]


def test_shutil_copy_in_session_requests_rio003(observe_lint):
    # Arrange
    src = _session(
        '    shutil.copy("data/in.csv", "out/in.csv")\n', imports="import shutil\n"
    )
    # Act
    req, emitted = _raw(observe_lint, src)
    # Assert
    assert (req, len(emitted)) == (["STX-RIO003"], _scitex())


def test_aliased_shutil_move_requests_rio003(observe_lint):
    # Arrange
    src = _session('    sh.move("a.csv", "b.csv")\n', imports="import shutil as sh\n")
    # Act
    req, _ = _raw(observe_lint, src)
    # Assert
    assert req == ["STX-RIO003"]


def test_open_in_helper_above_session_main_requests_pa002(observe_lint):
    # Arrange — regression: PA002 used to fire only for open() textually
    # AFTER the @stx.session decorator, so helpers above main slipped through.
    helpers = (
        "def write_results(path, text):\n"
        '    with open(path, "w") as f:\n'
        "        f.write(text)\n"
        "\n"
        "\n"
    )
    src = _session(imports="", helpers=helpers)
    # Act
    req, _ = _raw(observe_lint, src)
    # Assert
    assert req == ["STX-PA002"]


def test_research_script_dir_without_session_requests_rio001(observe_lint):
    # Arrange — a research project's scripts/ file is a research script
    # even before it has been decorated.
    src = 'from pathlib import Path\n\nPath("out.txt").write_text("x")\n'
    cfg = LinterConfig(project_types=["research"])
    # Act
    req, _ = _raw(observe_lint, src, filepath="scripts/pac/calc_pac.py", config=cfg)
    # Assert
    assert req == ["STX-RIO001"]


# --------------------------------------------------------------------------- #
# Negative — no false positives                                               #
# --------------------------------------------------------------------------- #


def test_library_module_without_session_requests_no_raw_io(observe_lint):
    # Arrange — library code writing a cache file is not research I/O.
    src = (
        "import shutil\n"
        "from pathlib import Path\n"
        "\n"
        "\n"
        "def cache(p, text):\n"
        "    Path(p).write_text(text)\n"
        '    shutil.copy(p, p + ".bak")\n'
        "    return open(p).read()\n"
    )
    # Act
    req, _ = _raw(observe_lint, src, filepath="src/pkg/_cache.py")
    # Assert
    assert req == []


def test_scripts_dir_outside_research_project_requests_no_raw_io(observe_lint):
    # Arrange — non-research project: scripts/ are shell utilities.
    src = 'from pathlib import Path\n\nPath("out.txt").write_text("x")\n'
    # Act
    req, _ = _raw(observe_lint, src, filepath="scripts/release/bump.py")
    # Assert
    assert req == []


def test_session_test_file_requests_no_raw_io(observe_lint):
    # Arrange
    src = _session('    Path("out.txt").write_text("x")\n')
    # Act
    req, _ = _raw(observe_lint, src, filepath="tests/test_run_analysis.py")
    # Assert
    assert req == []


def test_stx_io_save_and_load_request_no_raw_io(observe_lint):
    # Arrange
    src = _session(
        '    data = stx.io.load("./data/in.csv")\n'
        '    stx.io.save(data, "./results.csv")\n'
    )
    # Act
    req, _ = _raw(observe_lint, src)
    # Assert
    assert req == []


def test_non_shutil_copy_requests_no_rio003(observe_lint):
    # Arrange — dict.copy() / list.copy() are not file copies.
    src = _session("    d = {}\n    e = d.copy()\n", imports="")
    # Act
    req, _ = _raw(observe_lint, src)
    # Assert
    assert req == []


def test_non_path_open_attribute_requests_no_raw_io(observe_lint):
    # Arrange — webbrowser.open(url) is not file I/O on a Path.
    src = _session(
        '    webbrowser.open("https://example.org")\n', imports="import webbrowser\n"
    )
    # Act
    req, _ = _raw(observe_lint, src)
    # Assert
    assert req == []
