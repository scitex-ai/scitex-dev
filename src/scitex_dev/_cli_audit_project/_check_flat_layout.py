"""PS108 — flat package layout (common-prefix cluster) check.

Lives in its own module so `_audit.py` doesn't grow further. The audit
engine imports `check_flat_layout` and feeds it the same `Violation`
container used by sibling checks.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path


_CLUSTER_THRESHOLD = 3
_SKIP_STEMS = frozenset({"__init__", "__main__"})


def _prefix_token(stem: str) -> str:
    """First `_`-split token after stripping leading underscores.

    `_cli_audit` → `cli`, `_skills_quality` → `skills`, `cli` → `cli`.
    Empty string for stems that are all underscores.
    """
    bare = stem.lstrip("_")
    return bare.split("_", 1)[0] if bare else ""


def _scan_clusters(src_pkg: Path) -> dict[str, list[str]]:
    """Return {token: [filenames…]} for every prefix-cluster in `src_pkg`.

    Includes clusters of any size; caller decides which ones to flag.
    Skips files when a same-named subpackage already exists (refactor
    in progress) so we don't double-report the leftover stragglers.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for child in src_pkg.iterdir():
        if not child.is_file() or child.suffix != ".py":
            continue
        if child.stem in _SKIP_STEMS:
            continue
        token = _prefix_token(child.stem)
        if not token:
            continue
        if (src_pkg / token).is_dir() or (src_pkg / f"_{token}").is_dir():
            continue
        groups[token].append(child.name)
    return dict(groups)


def check_flat_layout(
    src_pkg: Path,
    violation_cls: type,
    out: list,
) -> None:
    """Append a single rolled-up PS108 per package when prefix-clusters exist.

    Rolling all clusters into one violation (rather than one per token)
    nudges the agent toward a coherent reorganization pass: when you
    refactor `_cli_*`, you also notice `_skills_*` and `_mcp_*` in the
    same directory and group them together, instead of fixing each
    cluster in isolation across separate PRs. The exact target dirs
    are a judgment call — the message asks for *logical* clustering,
    not blind prefix-promotion.
    """
    if not src_pkg.is_dir():
        return

    groups = _scan_clusters(src_pkg)
    flagged = {
        token: files
        for token, files in groups.items()
        if len(files) >= _CLUSTER_THRESHOLD
    }
    if not flagged:
        return

    # Sort clusters by size (largest first) so the loudest smell leads.
    ordered = sorted(flagged.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    summary_lines = []
    total_files = 0
    for token, files in ordered:
        total_files += len(files)
        sample = ", ".join(sorted(files)[:3])
        if len(files) > 3:
            sample += ", …"
        summary_lines.append(f"`{token}_*` ×{len(files)} ({sample})")

    detail = (
        f"{len(flagged)} prefix-clusters totaling {total_files} flat files "
        f"in `{src_pkg.name}/`: " + "; ".join(summary_lines) + ". "
        "Reorganize into logical subdirectories grouped by responsibility "
        "(not blind prefix-promotion). The CLI surface is a good model: if "
        "`<pkg> --help` already groups commands into Ecosystem / Development "
        "/ Documentation / Interface / Shell sections, the source layout "
        "should mirror those same categories — one subpackage per CLI "
        "category. Land all clusters in one coherent refactor pass; "
        "piecemeal cleanup leaves the directory half-organized for months."
    )
    out.append(violation_cls("PS108", str(src_pkg), detail))
