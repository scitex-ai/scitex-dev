---
description: |
  [TOPIC] Environment-local discovery and configuration
  [DETAILS] Configure installed CLI, skill and MCP provider preferences, inspect effective settings, and choose skill destinations. Dev dispatches leaf providers from its own Python environment; YAML preferences and CLI-managed overrides have explicit precedence.
tags: [scitex-dev-config, cli, skills, mcp, discovery]
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

An existing project-local `.scitex/dev/config.yaml` wins over the user default
through the shared config path resolver; explicit paths and `SCITEX_DEV_CONFIG`
still take priority over that default selection.

1. Ecosystem defaults (`cli_enabled`, `skills_enabled` and `mcp_enabled` default to true).
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
    cli_enabled: false
```

Use unquoted YAML booleans. The example disables Writer skill discovery while
leaving its MCP switch enabled and declining CLI aggregation. These fields are
independent; CLI off does not disable Python APIs, standalone executables or Web
routes. It is a selection preference, not authorization or proof of readiness. Omitted switches retain their current defaults.
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

from scitex_dev.exposure import load_exposure_policy
policy = load_exposure_policy()  # resolve selected config/state once
cli_switch = policy.is_enabled("scitex-writer", "cli")
unknown_mcp_preference = policy.is_enabled("unregistered-installed-owner", "mcp")
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


## Shared immutable exposure snapshot

The Python example above constructs the public snapshot once.

The same files and precedence apply even when an installed owner is absent from
ECOSYSTEM. Unconfigured owners default to enabled independently for CLI, MCP and
skills. `preferences` contains frozen configured-owner rows, not an installed
capability inventory. Subsequent file changes do not alter an existing snapshot;
construct a new view to refresh it. The query never rereads files or loads providers.

```bash
scitex-dev cli list --json       # raw installed declarations, not effective policy
scitex-dev cli status --json     # configured preferences, not callable providers
scitex-dev cli status --paths --json  # actual selected config/state locations
scitex-dev cli disable scitex-writer --yes
scitex-dev cli enable scitex-writer --yes
```

A compatible umbrella delegates these as `scitex dev cli ...`. Check actual
installed help: these new CLI controls and snapshot API require a version that
ships them. Consumers must explicitly apply the snapshot; writing a preference
cannot change an older host that does not consume it. Keep using standalone Dev
to restore a preference if a host hides its Dev aggregation namespace.

CLI YAML/state values must be real booleans: quoted `"false"`, null, numbers and
lists refuse rather than silently becoming true. The shared snapshot also refuses
malformed/unreadable state, invalid owner identities, conflicting canonical owners
and nonboolean state values for every surface. Missing files retain defaults and
are not created by reading. Existing supported skills/MCP YAML parsing is unchanged.
The CLI setter refuses malformed state before writing; it never repairs a corrupt
file by overwriting it. Use canonical distribution names, not command nicknames.

Installed CLI declaration `none`, invalid/ambiguous ownership and host admission
still deny mounting even when the preference is enabled. `list_cli_providers()`
remains an inert metadata reader and does not apply operator configuration. A
wrapper must retain its declared owner and aliases must resolve through the same
effective host view; preferences do not invent absent commands or enable endpoints.

`status --paths --json` returns `config_path`, `knob_state_path` and
`preferences`; ordinary `status --json` retains its owner-to-boolean mapping.
Only locations and selected booleans are shown, never raw configuration values.
The snapshot exposes the same frozen paths, so a project-local file shadowing a
home default is visible without adding another provenance registry.

These local package toggles are non-interactive. `--yes` is retained as a
compatibility flag; it does not add consent enforcement or authorization.
