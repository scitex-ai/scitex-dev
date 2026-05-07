"""Category IO: Call-level I/O rules (Phase 2)."""

from ._base import Rule

IO001 = Rule(
    id="STX-IO001",
    severity="warning",
    category="io",
    message="`np.save()` detected — use `stx.io.save()` for provenance tracking",
    suggestion="Replace `np.save(path, arr)` with `stx.io.save(arr, path)`.",
    requires="scitex",
)

IO002 = Rule(
    id="STX-IO002",
    severity="warning",
    category="io",
    message="`np.load()` detected — use `stx.io.load()` for provenance tracking",
    suggestion="Replace `np.load(path)` with `stx.io.load(path)`.",
    requires="scitex",
)

IO003 = Rule(
    id="STX-IO003",
    severity="warning",
    category="io",
    message="`pd.read_csv()` detected — use `stx.io.load()` for provenance tracking",
    suggestion="Replace `pd.read_csv(path)` with `stx.io.load(path)`.",
    requires="scitex",
)

IO004 = Rule(
    id="STX-IO004",
    severity="warning",
    category="io",
    message="`.to_csv()` detected — use `stx.io.save()` for provenance tracking",
    suggestion="Replace `df.to_csv(path)` with `stx.io.save(df, path)`.",
    requires="scitex",
)

IO005 = Rule(
    id="STX-IO005",
    severity="warning",
    category="io",
    message="`pickle.dump()` detected — use `stx.io.save()` for provenance tracking",
    suggestion="Replace `pickle.dump(obj, f)` with `stx.io.save(obj, 'file.pkl')`.",
    requires="scitex",
)

IO006 = Rule(
    id="STX-IO006",
    severity="warning",
    category="io",
    message="`json.dump()` detected — use `stx.io.save()` for provenance tracking",
    suggestion="Replace `json.dump(obj, f)` with `stx.io.save(obj, 'file.json')`.",
    requires="scitex",
)

IO007 = Rule(
    id="STX-IO007",
    severity="warning",
    category="io",
    message="`.savefig()` detected — use `stx.io.save(fig, path)` for metadata embedding",
    suggestion="Replace `fig.savefig(path)` with `stx.io.save(fig, path)`.",
    requires="scitex",
)
