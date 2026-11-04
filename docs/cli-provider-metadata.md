# Installed CLI exposure

Inspect decisions with `scitex dev cli list --json` (umbrella) or
`scitex-dev cli list --package scitex-sdk --json` (standalone). These commands
forward the public reader rows only; they never execute discovered commands.

CLI eligibility is independent of Python imports, MCP tools, Web admission and
skills. Hosts read `from scitex_dev.cli_providers import list_cli_providers`.
This metadata-only reader never loads entry points or imports leaf commands.
It discovers installed distributions, including owners outside the curated
ECOSYSTEM registry. It does not execute a CLI or prove it is a Click command.

A leaf can declare a canonical command in its existing packaging metadata:

```toml
[project.entry-points."scitex.cli"]
research = "owned_package.cli:main"
```

Names are lowercase kebab-case tokens. Targets are dotted Python
`module:attribute` references, without extras or shell syntax. The module must
be declared in the owner's installed files, or proved by a conventional local
editable installation. For editable installs the reader requires an editable
`direct_url.json` file URL, matching `[project].name`, exactly one target under
the source root or `src/`, and resolved containment. It never evaluates `.pth`
files. Custom layouts without proof are unavailable, with an explicit reason.
These checks are installed/source metadata evidence, not executable admission
or an assertion about arbitrary later `sys.path` mutations.

To explicitly decline CLI mounting while retaining other interfaces:

```toml
[project.entry-points."scitex.cli"]
research = "none"
```

The literal `none` is reserved and never loaded. Any explicit CLI declaration
suppresses console fallback for that owner. Opt-out names remain reserved
across registry and wrapper fallback, even when the wrapper has another owner.

`list_cli_providers(package=None, path=None)` returns a frozen tuple of frozen
`CliProvider` rows: `name`, `target`, `distribution`, `version`, `status`,
`source`, `console_script`, `reason`. The optional `package` filters normalized
owning distribution identities; `path` selects installed metadata search roots.
Ambiguity is computed before filtering.

| Status | Meaning |
| --- | --- |
| `absent` | No explicit declaration or eligible canonical console evidence. |
| `none` | Explicit CLI opt-out; reserve the name, do not mount it. |
| `declared` | Valid explicit metadata with owned module evidence; validate lazily on invocation. |
| `legacy_unknown` | Eligible canonical console evidence; invocation and Click compatibility remain unknown. |
| `invalid` | Invalid name/target/owner or unprovable target ownership; do not fall back. |
| `ambiguous` | Duplicate installed owners or command names; retain every row and deny that name. |

Legacy evidence is limited to a console script named exactly after a
`scitex-*` distribution or the known brands `figrecipe`, `socialia`, `newb`,
`crossref-local`, `openalex-local`. It strips `scitex-` for the candidate command
name and maps `socialia` to `social`. This does not discover arbitrary tools
such as `pytest` or `uv`. No-console does not mean Python/MCP/skills are absent;
a host may separately own explicit wrappers without claiming a leaf console.

Consumers must reserve every named non-eligible row, refuse ambiguous names,
apply independent host naming/retirement policy, and load targets only on
invocation. A hidden deprecated alias must resolve the effective canonical
command, so an alias cannot resurrect a disabled target. The reader never applies operator configuration. The separate
`scitex_dev.exposure.load_exposure_policy()` snapshot supplies independent CLI,
MCP and skills preferences; hosts must combine CLI eligibility with that policy.
`scitex-dev cli status/enable/disable` manages the CLI preference using existing
configuration/state files. This does not revoke standalone binaries or enable
other interfaces.

Repeated searches of the same physical metadata origin are deduplicated. A
setuptools editable source egg-info shadow is collapsed only when its canonical
location is directly under the proved editable root or `src/`, its complete
PKG-INFO bytes equal installed METADATA, version and every entry point match.
Separate installed dist-info directories and differing source metadata remain
ambiguous. This is a same-install identity proof, not owner/version-only dedup.
