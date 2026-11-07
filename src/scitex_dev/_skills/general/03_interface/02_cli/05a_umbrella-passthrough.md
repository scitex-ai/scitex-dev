---
description: |
  [TOPIC] Umbrella CLI delegation
  [DETAILS] Project eligible, operator-enabled leaf CLI providers without cloning their command catalogs or mutating shared Click objects. Keep explicit opt-outs, ownership ambiguity, qualified ordinary launchers and effective command paths visible.
tags: [scitex-general-interface-cli-umbrella-passthrough]
---

# Umbrella CLI delegation

The umbrella owns its namespace and composition policy. Each leaf owns its
command behavior, parameters, descriptions, output and exit semantics. A Python
package being importable does not automatically make it a public CLI group.

## Declare installed eligibility

A leaf declares CLI exposure through package metadata:

```toml
[project.entry-points."scitex.cli"]
example = "example_package.cli:main"
```

This is an authoring template: replace the names with the actual owner and
callable. A value of `none` explicitly opts out. Inspect metadata through
`scitex_dev.cli_providers.list_cli_providers`; declarations, effective operator
preferences and validated callability are different observations.

The dispatcher must preserve explicit opt-outs, reserve conflicting/invalid
names and reject ambiguous ownership. A legacy console-script clue is not the
same as a verified provider declaration. See the source contract in
`docs/cli-provider-metadata.md`.

## Click registration without owner mutation

Click composes the command path from the parent context. A named attachment can
preserve the leaf object while giving it an umbrella path:

```python
import click

@click.group()
def leaf():
    """An owned example leaf."""

@leaf.command()
def status():
    """Show the example status."""
    click.echo("ready")

umbrella = click.Group("scitex")
umbrella.add_command(leaf, name="example")
```

Here `umbrella example status` and `leaf status` share the command definition.
The registered path does not require assigning to `leaf.name`. Production Root
uses its installed provider registry and explicit adapters rather than this
manually constructed demonstration group.

Preserve the shared owner object, its help, completion, flags and execution
semantics. Umbrella-owned workflow composition may use a deliberate view, and
an exactly metadata-qualified ordinary launcher can use its owned adapter;
neither is permission to copy a foreign command catalog into another package.

## Help and compatibility

Use the shared `CliHelp`, `SpecCommand` and `SpecGroup` facilities with
context-aware `{prog}` examples where applicable. Do not rewrite a command's
help during its callback: help is requested before that callback runs, and
mutating the shared object can leak into other mounts.

Keep deliberate legacy aliases hidden and point them at the effective command
path. The shared `deprecated_alias` helper supports tuple paths such as
`("dev", "skills")`; do not implement another namespace parser for the same job.
Operator CLI preferences govern aggregation, not standalone execution, Python,
MCP, skills or Web admission.

## Verify behavior

Check public help, actual arguments/output/exit codes, completion, legacy alias
routing and ownership under the installed composition. Generic install guidance
must not disguise a broken internal import as an absent optional package.

- [05_pass-through.md](05_pass-through.md): forwarding to upstream executables.
- [10_help-format.md](10_help-format.md): shared command-help contracts.
- [MCP registration](../03_mcp/02_server-registration.md): leaf registration and
  dispatcher exposure for protocol tools.
