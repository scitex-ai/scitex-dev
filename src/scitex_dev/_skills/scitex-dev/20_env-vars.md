---
description: |
  [TOPIC] Environment variables
  [DETAILS] Selected runtime settings and their owning readers: configuration and package switches, audit registry, legacy HPC helpers, skill export and shell completion. Inspect each consumer; precedence and diagnostic coverage are not universal.
tags: [scitex-dev-env-vars]
---

# Environment variables

These are selected settings, not a complete inventory of every Dev subsystem.
Precedence belongs to the reader: a CLI flag only overrides an environment value
when that command implements the connection. See [12_config.md](12_config.md)
for package preferences and the separate machine-managed state overlay.

## Configuration and registry

| Variable | When unset | Owning reader and meaning |
|---|---|---|
| `SCITEX_DEV_CONFIG` | Shared resolver selects the Dev config; normally `~/.scitex/dev/config.yaml`, with project/legacy fallbacks described in the config guide | `_core/config.py`: selects the YAML path; explicit `load_config(config_path=...)` takes priority |
| `SCITEX_DEV_KNOB_STATE` | Shared state path, normally `~/.scitex/dev/runtime/knob-state.json` | `_core/_knobs.py`: CLI-managed package switches overlay YAML preferences |
| `SCITEX_DEV_HOSTS` | Preserve configured host enablement | `_core/config.py`: a nonempty comma-separated selection replaces enabled flags for configured hosts; it does not discover or create hosts |
| `SCITEX_DEV_GITHUB_REMOTES` | Preserve configured remote enablement | `_core/config.py`: a nonempty comma-separated selection replaces enabled flags for configured GitHub remotes |
| `SCITEX_DEV_REGISTRY` | Project `.scitex/dev/ecosystem.yaml`, then user equivalent, then bundled ecosystem mapping | `_cli/audit/_summary/_audit.py::_load_registry`: supported audit consumers prefer an existing explicit registry file, then an existing environment-selected file, then those fallbacks |
| `SCITEX_DEV_NO_DRIFT_WARN` | Drift checker remains eligible to run | `_release/check_editable_drift.py::check`: any nonempty value returns no drift warning when this checker is called |

`SCITEX_DIR` affects the shared root resolver. A selected path need not exist;
reading missing config/state retains the reader's defaults without creating it.
The audit registry loader tries existing files and merges the first selected
mapping over bundled entries; an override is not an entirely separate roster.
Malformed input handling is reader-specific. Do not assume every auditor reads
this registry or every command uses `load_config`.

The editable-drift check runs from eligible CLI invocation paths, not from a
plain library import. It is not a general environment-variable diagnostic.

## Legacy HPC helpers (`SCITEX_DEV_TEST_*`)

`test_runner.py::_get_hpc_config` passes explicit `TestConfig` fields to
`PriorityConfig(env_prefix="SCITEX_DEV_TEST_")`: direct field, environment, then
the defaults below. This does not establish a Dev YAML reader for these fields.

| Variable | Default | Meaning |
|---|---|---|
| `SCITEX_DEV_TEST_HOST` | `spartan` | HPC SSH hostname |
| `SCITEX_DEV_TEST_CPUS` | `16` | CPUs per Slurm task; resolved as an integer |
| `SCITEX_DEV_TEST_PARTITION` | `sapphire` | Slurm partition |
| `SCITEX_DEV_TEST_TIME` | `00:20:00` | Slurm time limit |
| `SCITEX_DEV_TEST_MEM` | `128G` | Slurm memory request |
| `SCITEX_DEV_TEST_REMOTE_BASE` | `~/proj` | Remote project base |

See [43_hpc-test-runner.md](43_hpc-test-runner.md) for the individual submit,
poll and fetch consumers. Local pytest is separate; these defaults are not
proof of a reachable host, scheduler admission or successful remote execution.

## Skill export

`SCITEX_DEV_SKILLS_DEFAULT_EXPORT_DIR` selects the default for the legacy export
consumer in `_ecosystem/_skills/skills.py::_get_default_export_dest` and its drift
reader. Its fallback is `~/.claude/skills/scitex/`; an explicit export destination
wins. This does not relocate the neutral `skills install` store or configure all
agent clients. Use the current standalone `scitex-dev dev skills ...` route;
umbrella availability depends on the installed adapter.

Keep destinations outside Git authority and preserve ownership/conflict checks.
See [36_skill-registry.md](36_skill-registry.md) and
[41_agent-setup.md](41_agent-setup.md) for installation and actual client adoption.

## Shell completion

`_SCITEX_DEV_COMPLETE` is Click's internal completion request variable, not a
normal configuration setting. Print the current script or preview installation:

```bash
scitex-dev print-shell-completion --shell bash
scitex-dev install-shell-completion --shell bash --dry-run
```

Actual installation writes shell startup/completion files. The retired
`install-tab-completion` alias exits 2 with a rename message; it does not install.
For bash/zsh, the current installer writes a cached script and sources that file
from the startup file; the former per-startup eval line is legacy behavior.

## Inspect the relevant consumer

```bash
scitex-dev show-config --json
scitex-dev cli status --paths --json
scitex-dev doctor --help
```

`show-config --json` serializes resolved configuration; it does not attach
per-value provenance or report every environment variable. `cli status --paths`
reports the exposure policy's selected config/state locations and preferences.
The doctor's environment check inspects `SCITEX_DIR`, `SCITEX_MCP_USE_*` and
variables containing both `SCITEX` and `DISABLE`, not this entire table. The full
doctor also checks packages/PyPI, MCP and agent sessions; help alone runs none of
those checks.

Owning behavioral controls: `_core/test_config.py`, `_core/test_config_knobs.py`
and `_core/test_config_knob_persistence.py` under `tests/scitex_dev/`;
`tests/scitex_dev/_cli/test__completion.py`,
`tests/scitex_dev/_cli/test__root_drift_silence.py` and
`tests/scitex_dev/_cli/audit/_summary/test__audit.py`. Those selected controls do
not certify every variable, command, remote host, exported client or prose claim.
