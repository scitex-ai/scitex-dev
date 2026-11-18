"""Create actual installed metadata in an owned directory."""


def distribution(
    root,
    owner="owned-example",
    *,
    name=None,
    target="missing_provider:get_nodes",
    group="scitex_dev.hierarchy",
    version="1.2.3",
    slot="one",
):
    info = root / f"owned_{slot}-1.2.3.dist-info"
    info.mkdir(parents=True)
    lines = ["Metadata-Version: 2.1", f"Name: {owner}", "Summary: Owned hierarchy"]
    if version is not None:
        lines.append(f"Version: {version}")
    (info / "METADATA").write_text("\n".join(lines) + "\n")
    declared = name or owner.lower().replace("_", "-").replace(".", "-")
    (info / "entry_points.txt").write_text(f"[{group}]\n{declared} = {target}\n")
    return info
