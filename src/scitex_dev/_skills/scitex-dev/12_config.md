---
description: |
  [TOPIC] Environment-local discovery and configuration
  [DETAILS] Configure installed skill and MCP provider opt-outs, inspect effective settings, and choose skill destinations. Dev dispatches leaf providers from its own Python environment; YAML preferences and CLI-managed overrides have explicit precedence.
tags: [scitex-dev-config, skills, mcp, discovery]
---

# Configuration and installed-provider discovery

## Ownership and defaults

Dev is the dispatcher; each leaf owns its provider declarations, skills, hooks,
and expert checks. Installed skill discovery reads `scitex_dev.skills` entry-point
metadata visible to the Python interpreter running Dev. It does not search every
checkout in `~/proj`, import every package, or use another agent's cache as a source.
Editable installations count when their distribution metadata and resources are
reachable in that environment. Installing a package in another virtual environment
or container does not make it visible here.

Default: include all installed, registered skill providers unless their owning
distribution is opted out. A provider declaration is not proof that its tools run
successfully. Missing declarations/resources and ambiguous ownership must remain
visible; do not silently substitute another package or checkout.

## Files and precedence

| Purpose | Default location | Override |
|---|---|---|
| Hand-authored preferences | `~/.scitex/dev/config.yaml` | `SCITEX_DEV_CONFIG` or explicit `load_config(config_path=...)` |
| CLI-managed package switches | `~/.scitex/dev/runtime/knob-state.json` | `SCITEX_DEV_KNOB_STATE` |
| Generated neutral skill store | `~/.scitex/dev/skills/` | `skills install --dest ...` |

`SCITEX_DIR` relocates the shared `.scitex` root. The legacy
`~/.scitex/dev_config.yaml` is a fallback only when the preferred file is absent.
A default path can exist as a convention without the file having been created.

Effective per-package switches resolve as:

1. Ecosystem defaults (`skills_enabled` and `mcp_enabled` default to true).
2. Matching `packages` entries in the selected YAML file.
3. CLI-managed entries in `knob-state.json`, which take precedence over YAML.

A YAML change can therefore appear ineffective if a prior CLI override remains.
Inspect the effective state and that specific override before changing settings.
Do not remove another package's state or rewrite the entire configuration file.

## Opt out by owning distribution

```yaml
packages:
  - name: scitex-writer
    skills_enabled: false
    mcp_enabled: true
```

Use unquoted YAML booleans. The example disables Writer skill discovery while
leaving its MCP switch enabled. Omitted switches retain their current defaults.
A skill namespace can differ from its owner: SDK owns `scitex-app` and `scitex-ui`,
so their owner-level switch is `scitex-sdk`. Package selection does not authorize
a conflicting or undeclared namespace.

Inspect the selected file and resolved settings without modifying them:

```python
from scitex_dev import get_config_path, load_config

selected_file = get_config_path()
resolved = load_config()
skill_switches = {package.name: package.skills_enabled for package in resolved.packages}
mcp_switches = {package.name: package.mcp_enabled for package in resolved.packages}
```

For installed umbrella versions exposing Dev's CLI passthrough:

```bash
scitex dev dev skills status --json
scitex dev mcp status --json
scitex dev dev skills disable scitex-writer --dry-run
```

Omit `--dry-run` only when applying the requested change. The `enable` and
`disable` commands write the machine-managed JSON state, not the YAML file.
The standalone equivalent replaces the `scitex dev` prefix with `scitex-dev`.
Check actual installed help before assuming a different version exposes that path.
These switches do not uninstall packages or change already-running client context;
consuming dispatchers must honor them and refresh their projections/server state.

## Availability, installation, and context are separate

Discovery should make eligible installed skills available. It should not load
all skill bodies or advertise every installed tool in every agent's context.
Select packages or skills for a workflow, then load more through discovery when
needed. Keep leaf resources authoritative and generated stores reproducible.

```bash
scitex dev dev skills list --package scitex-dev --json
scitex dev dev skills install --package scitex-dev --dry-run --json
scitex dev dev skills install --package scitex-dev --dest /path/to/owned/skills --dry-run --json
```

Without `--package`, installed discovery includes all enabled registered owners.
A full install can correctly refuse if retired and replacement distributions both
claim one namespace. Inspect ownership; do not hide the collision or delete packages
without a deliberate retirement decision. A scoped refresh preserves other owners.

`--dest` chooses the generated store, not a universal agent vendor configuration.
Link selected skill folders into the directory supported by that agent, preserving
existing files and reporting conflicts. Do not assume that linking the whole store
will be discovered identically by every client. The legacy Claude-specific flag
remains a compatibility option, not the default setup model.

## Source-backed verification

Check current CLI help, resolved switches and actual installed provider metadata
when diagnosing behavior. Compare exported skills with their owning package's
projection manifest and hashes. A source edit, a published version, a generated
store, and an agent loading that store are separate observations.

The existing CI matrix runs on pull requests and nightly at 17:00 UTC. Configuration
regressions exercise these examples against isolated files and CLI commands there;
this does not certify every documentation example. The read-only documentation
verifier reports its static scope and unverified cases rather than equating valid
Python syntax with successful execution.

See [36_skill-registry.md](36_skill-registry.md) for ownership/projection checks,
[41_agent-setup.md](41_agent-setup.md) for setup and protocol qualification, and
[42_context-discovery.md](42_context-discovery.md) for selective MCP exposure and
honest metadata accounting.
