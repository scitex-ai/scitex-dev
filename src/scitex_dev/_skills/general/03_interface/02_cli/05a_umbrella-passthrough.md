---
description: |
  [TOPIC] Interface Cli Umbrella Passthrough
  [DETAILS] Umbrella `scitex` projects eligible, operator-enabled CLI providers: Click commands retain owner identity; an exact metadata-qualified ordinary console launcher uses the owned adapter. Branded packages (e.g. socialia → `scitex social`) rewrite the program name on mount.
tags: [scitex-general-interface-cli-umbrella-passthrough]
---

# §5b. Umbrella subcommand passthrough — single source of truth

> One sentence: **the umbrella owns the namespace; the package owns its surface; the umbrella never re-types what the package already declares.**

This is distinct from §1c (tool pass-through to upstream binaries). §1c forwards to non-scitex tools (`git`, `uv`); §5b connects the umbrella `scitex` to a standalone `scitex-<pkg>` (or branded sibling like `socialia`) that already ships its own click tree.

## The rule

When a `scitex-<pkg>` package declares an eligible CLI and operator policy enables it, the umbrella can expose its canonical command. A CLI declaration is not automatic mounting: explicit `none`, ambiguity and independent CLI preferences remain deny gates. For a direct Click provider, preserve the re-exported command/group object:
its leaf help, examples, sub-tree and completion remain owned by the standalone.
The umbrella owns namespace selection, install guidance and deliberate shared
workflow/developer composition; these are not universal byte-for-byte Group
mounts. A metadata-qualified ordinary console launcher can use the owned adapter
rather than a Click re-export. Keep each adaptation explicit and preserve leaf
arguments, output and exit semantics without cloning the leaf's command catalog.

### Canonical shim

```python
# scitex-python: src/scitex/cli/<short>.py
import click

try:
    from scitex_<pkg>._cli import main as _main  # branded: e.g. `from socialia._cli import main as _main`
except ImportError:
    _main = None

if _main is not None:
    <short> = _main
    <short>.name = "<short>"   # ← rewrites prog-name fragment shown under `scitex`
else:
    @click.command("<short>")
    def <short>():
        """scitex-<pkg> not installed."""
        click.secho("Install with: pip install scitex-<pkg>", fg="red")
        raise SystemExit(1)
```

Click composes the `Usage:` line from the parent command path, so `scitex <short> --help` automatically renders `Usage: scitex <short> [OPTIONS] ...` even though the standalone renders `Usage: scitex-<pkg> [OPTIONS] ...`. **No duplication, no drift.**

### Forbidden anti-pattern

```python
# DO NOT do this
_DATASET_COMMANDS = {"openneuro": "Fetch from OpenNeuro", ...}

@click.command("dataset")
@click.argument("args", nargs=-1)
def dataset(args):
    """Hand-typed help that drifts the moment scitex-dataset reshapes."""
    subprocess.call(["scitex-dataset", *args])
```

This loses click context, env-var inheritance, exit-code semantics, tab-completion, `--help-recursive`, and — most importantly — drifts the moment the standalone CLI grows or reshapes. The 2026-05-06 dataset escalation (`GITIGNORED/ESCALATION.md`) was filed because exactly this shape masked the standalone's migration from flat (`openneuro / dandi`) to 3-level (`<domain> <dataset> <action>`) for an entire release cycle.

## Branded packages (program-name rewriting)

Some downstream packages do not carry the `scitex-` prefix (`socialia`, `figrecipe`, `newb`). When mounted under the umbrella, the program-name fragment must also be rewritten:

| Standalone invocation        | Umbrella invocation         | How                                                    |
|------------------------------|-----------------------------|--------------------------------------------------------|
| `scitex-dataset --help`      | `scitex dataset --help`     | `dataset = _ds_main; dataset.name = "dataset"`         |
| `socialia --help`            | `scitex social --help`      | `social = _socialia_main; social.name = "social"`      |
| `figrecipe --help`           | `scitex plt --help`         | `plt = _figrecipe_main; plt.name = "plt"` (mount-only) |

**Both** invocations must keep working — the standalone keeps its own brand, the umbrella shows its namespace. Click handles this naturally via the parent command path.

### Help text inside the standalone

Standalone help/examples/epilogs MUST avoid hardcoded `scitex-<pkg>` / brand strings where the same line will be rendered under the umbrella. Two acceptable patterns:

1. **Reference the running prog name from context:**
   ```python
   @click.command()
   @click.pass_context
   def fetch(ctx):
       """Fetch a dataset.

       \b
       Examples:
         $ {prog} fetch openneuro ds000001
       """
       fetch.help = fetch.help.format(prog=ctx.find_root().info_name)
   ```

2. **Use a brand-neutral placeholder** (`<cli>` is the existing convention in this skill set — see [10_help-format.md](10_help-format.md)) and document it in the package's own README. The auditor accepts `<cli>` as a non-violation.

The brand-rewrite registry — which package ships under which umbrella subcommand name — lives in the ecosystem registry (`scitex_dev._ecosystem._core.ECOSYSTEM`) under the optional `umbrella_subcommand` field. If absent, the auditor assumes `<short>` = the package name with `scitex-` stripped.

## Adoption checklist

For each `scitex-<pkg>` (or branded sibling) the maintainer must:

- [ ] Replace `scitex-python: src/scitex/cli/<short>.py` with the re-export shim above.
- [ ] Confirm `scitex <short> --help` is byte-identical to the standalone `--help` (modulo the program-name fragment in `Usage:`).
- [ ] Confirm the standalone's help text contains no hardcoded `scitex-<pkg>` / brand strings — use `{prog}` or `<cli>` instead.
- [ ] If branded (no `scitex-` prefix), add `umbrella_subcommand: "<short>"` to the package's `ECOSYSTEM` entry.
- [ ] Run `scitex-dev ecosystem audit-cli scitex-<pkg>` and confirm the umbrella-drift section is clean.

## See also

- [05_pass-through.md](05_pass-through.md) — verbatim forwarding to **upstream** binaries (`git`, `uv`). Different concept.
- MCP equivalent: [03_interface/03_mcp/02_server-registration.md](../03_mcp/02_server-registration.md) — `safe_mount(..., namespace="<short>")`.
- Source escalation: `GITIGNORED/ESCALATION.md` (2026-05-06, scitex-dataset audit).

## Installed command eligibility

Declare leaf CLI exposure through `[project.entry-points."scitex.cli"]`:
`name = "owned_package.cli:main"`, or `name = "none"` for explicit CLI opt-out.
This is independent of Python, MCP and skills. Hosts use the public metadata-only
`scitex_dev.cli_providers.list_cli_providers`; they must reserve opted-out and
invalid names, refuse all ambiguous names, and validate callability at invocation.
Canonical legacy console evidence is labeled `legacy_unknown`, never verified
CLI support. See `docs/cli-provider-metadata.md` for ownership proof and migration.

Use `deprecated_alias(..., target=("dev", "skills"), ...)` for a nested hidden
alias. Tuple paths resolve lazily through effective `get_command` policy and
forward target help; do not create a second alias dispatcher or split arbitrary
space-containing strings into command paths.

The exact metadata-qualified ordinary-console adapter is distinct from guessing
a binary or cloning a leaf CLI. CLI preferences govern aggregation only, not
standalone execution, Python imports, MCP, skills or Web admission.
