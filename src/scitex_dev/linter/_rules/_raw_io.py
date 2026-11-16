"""Category RIO: raw stdlib file I/O that bypasses ``stx.io`` (STX-RIO001-003).

The scitex-io plugin's STX-IO001-015 cover *library* writers/readers
(numpy, pandas, pickle, json, yaml, torch, ...), and STX-PA002 covers the
bare ``open()`` builtin. Neither sees the stdlib escape hatches an agent
reaches for when it "just wants to write a file":

- ``Path(p).write_text(s)`` / ``Path(p).write_bytes(b)`` / ``Path(p).open("w")``
- ``Path(p).read_text()``   / ``Path(p).read_bytes()``   / ``Path(p).open()``
- ``shutil.copy/copy2/copyfile/copytree/move(src, dst)``

Every one of these writes or reads a research artefact that clew then
cannot see: no input/output edge is recorded, so ``clew chain`` on the
result is empty (hands-on finding, 2026-11: an agent wrote results via
``Path.write_text`` and raw ``open()`` and nothing caught it).

False-positive control lives in the checker (``_checks/_raw_io.py``): the
rules only fire in RESEARCH SCRIPTS — a module that declares an
``@stx.session`` / ``@stx.module`` entry point, or a file under a configured
``script_dirs`` entry of a ``project-type: research`` project — and never
in test files. Library code under ``src/`` writing a cache file is not
flagged.
"""

from ._base import Rule

_ALLOW_HINT = (
    "\nIf this file op is genuinely NOT research data (a lock file, a log the\n"
    "session already captures), say so on the line:\n"
    "  ...  # stx-allow: {rid}  (reason: <why this is not data>)"
)

RIO001 = Rule(
    id="STX-RIO001",
    severity="warning",
    category="io",
    message=(
        "Raw pathlib write (`.write_text()`/`.write_bytes()`/`.open('w')`) — "
        "the output bypasses stx.io, so clew records NO output edge for it"
    ),
    suggestion=(
        "Write through stx.io so the file joins the session's provenance:\n"
        "  Path('results.txt').write_text(text)   ->  stx.io.save(text, './results.txt')\n"
        "  Path('r.json').write_text(json.dumps(d)) ->  stx.io.save(d, './r.json')\n"
        "  Path('blob.bin').write_bytes(b)         ->  register_saver('.bin') + stx.io.save(b, './blob.bin')"
        + _ALLOW_HINT.format(rid="STX-RIO001")
    ),
    requires="scitex",
)

RIO002 = Rule(
    id="STX-RIO002",
    severity="warning",
    category="io",
    message=(
        "Raw pathlib read (`.read_text()`/`.read_bytes()`/`.open()`) — the "
        "input bypasses stx.io, so clew records NO input edge for it"
    ),
    suggestion=(
        "Read through stx.io so the file joins the session's provenance:\n"
        "  Path('data/in.csv').read_text()  ->  stx.io.load('./data/in.csv')\n"
        "  Path('cfg.yaml').read_text()     ->  CONFIG (injected by @stx.session) or stx.io.load('./cfg.yaml')\n"
        "  Path('blob.bin').read_bytes()    ->  register_loader('.bin') + stx.io.load('./blob.bin')"
        + _ALLOW_HINT.format(rid="STX-RIO002")
    ),
    requires="scitex",
)

RIO003 = Rule(
    id="STX-RIO003",
    severity="warning",
    category="io",
    message=(
        "`shutil` copy/move of a file — the destination has no producing-"
        "session edge and the source no consuming edge in clew"
    ),
    suggestion=(
        "Route the data through stx.io so both ends are recorded:\n"
        "  shutil.copy('data/in.csv', 'out/in.csv')  ->  stx.io.save(stx.io.load('./data/in.csv'), './in.csv')\n"
        "For a format stx.io cannot load, register a loader/saver for its\n"
        "extension (`register_loader` / `register_saver`) instead of copying bytes."
        + _ALLOW_HINT.format(rid="STX-RIO003")
    ),
    requires="scitex",
)

__all__ = ["RIO001", "RIO002", "RIO003"]
