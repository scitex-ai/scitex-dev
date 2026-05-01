"""PS501 / PS502 — examples conventions.

PS501: every `.py` example whose stem starts with NN_ should decorate
its `main()` with `@stx.session`. The reference is
`~/proj/figrecipe/examples/01_bundle_format.py` and
`~/proj/scitex-python/examples/01_session.py`. The decorator gives
auto-CLI, SDIR_RUN-managed output, config injection, reproducibility.

PS502: an example file `<n>.py` with a sibling directory `<n>_out/`
that is empty (or contains only `__pycache__`) means the example was
never run end-to-end — fix the example or delete the empty stub.
"""

from __future__ import annotations

import re
from pathlib import Path


_NUMBERED_EXAMPLE_RE = re.compile(r"^\d+_[A-Za-z0-9_]+\.py$")
_STX_SESSION_RE = re.compile(r"@\s*stx\.session\b|@\s*stx\.module\b")
_HAS_DEF_MAIN = re.compile(r"^\s*(?:async\s+)?def\s+main\s*\(", re.MULTILINE)


def _is_empty_or_pycache_only(d: Path) -> bool:
    if not d.is_dir():
        return False
    children = [p for p in d.iterdir() if p.name != "__pycache__"]
    return not children


def check_examples_conventions(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS501 / PS502 violations for examples/ contents."""
    examples = repo / "examples"
    if not examples.is_dir():
        return

    for child in examples.iterdir():
        if not child.is_file() or not _NUMBERED_EXAMPLE_RE.match(child.name):
            continue
        try:
            text = child.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Only flag PS501 if the example actually defines main() — pure
        # imperative scripts that fall through top-level are a separate
        # legacy pattern PS503 might cover later.
        if not _HAS_DEF_MAIN.search(text):
            continue
        if _STX_SESSION_RE.search(text):
            continue
        out.append(
            violation_cls(
                "PS501",
                str(child),
                (
                    "main() not decorated with @stx.session. Wrap it: "
                    "`import scitex as stx; @stx.session\\n"
                    "def main(CONFIG=stx.session.INJECTED, "
                    "logger=stx.session.INJECTED): ...` and use "
                    "`Path(CONFIG.SDIR_RUN)` for outputs."
                ),
            )
        )

    # PS502: empty <n>_out/ siblings.
    for child in examples.iterdir():
        if not child.is_dir() or not child.name.endswith("_out"):
            continue
        if _is_empty_or_pycache_only(child):
            out.append(
                violation_cls(
                    "PS502",
                    str(child),
                    (
                        "empty examples output dir — the example was never "
                        "run end-to-end. Run it once to populate the "
                        "FINISHED_SUCCESS marker, or delete the empty stub."
                    ),
                )
            )
