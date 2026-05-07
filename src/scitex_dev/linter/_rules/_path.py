"""Category PA: Path handling rules."""

from ._base import Rule

PA001 = Rule(
    id="STX-PA001",
    severity="warning",
    category="path",
    message="Absolute path in `stx.io` call — use relative paths for reproducibility",
    suggestion="Use `stx.io.save(obj, './relative/path.ext')` — paths resolve to script_out/.",
    requires="scitex",
)

PA002 = Rule(
    id="STX-PA002",
    severity="warning",
    category="path",
    message="`open()` detected — use `stx.io.save()`/`stx.io.load()` which includes auto-logging",
    suggestion=(
        "Replace `open(path)` with `stx.io.load(path)` or `stx.io.save(obj, path)`.\n"
        "  stx.io automatically logs all I/O operations for provenance tracking."
    ),
    requires="scitex",
)

PA003 = Rule(
    id="STX-PA003",
    severity="info",
    category="path",
    message="`os.makedirs()`/`mkdir()` detected — `stx.io.save()` creates directories automatically",
    suggestion=(
        "Remove manual directory creation.\n"
        "  `stx.io.save(obj, './subdir/file.ext')` auto-creates `subdir/` inside script_out/."
    ),
    requires="scitex",
)

PA004 = Rule(
    id="STX-PA004",
    severity="warning",
    category="path",
    message="`os.chdir()` detected — scripts should be run from project root",
    suggestion="Remove `os.chdir()` and run scripts from the project root directory.",
)

PA005 = Rule(
    id="STX-PA005",
    severity="info",
    category="path",
    message="Path without `./` prefix in `stx.io` call — use `./` for explicit relative intent",
    suggestion="Use `./filename.ext` instead of `filename.ext` to clarify relative path intent.",
    requires="scitex",
)
