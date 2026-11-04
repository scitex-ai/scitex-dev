# SciTeX Dev (`scitex-dev`)

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-logo-blue-cropped.png" alt="SciTeX" width="400">
  </a>
</p>

<p align="center"><b>Shared developer utilities for the SciTeX ecosystem</b></p>

<p align="center">
  <a href="https://scitex-dev.readthedocs.io/">Full Documentation</a> · <code>uv pip install scitex-dev[all]</code>
</p>

<!-- scitex-badges:start -->
<p align="center">
  <a href="https://pypi.org/project/scitex-dev/"><img src="https://img.shields.io/pypi/v/scitex-dev?label=PyPI" alt="PyPI"></a>
  <a href="https://pypi.org/project/scitex-dev/"><img src="https://img.shields.io/pypi/pyversions/scitex-dev?label=Python" alt="Python"></a>
  <a href="https://github.com/scitex-ai/scitex-dev/actions/workflows/rtd-sphinx-build-on-ubuntu-latest.yml"><img src="https://img.shields.io/github/actions/workflow/status/scitex-ai/scitex-dev/rtd-sphinx-build-on-ubuntu-latest.yml?branch=develop&label=RTD" alt="RTD"></a>
  <a href="https://www.gnu.org/licenses/agpl-3.0"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg?label=License" alt="License"></a>
</p>
<p align="center">
  <a href="https://github.com/scitex-ai/scitex-dev/actions/workflows/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml"><img src="https://img.shields.io/github/actions/workflow/status/scitex-ai/scitex-dev/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml?branch=develop&label=Tests" alt="Tests"></a>
  <a href="https://github.com/scitex-ai/scitex-dev/actions/workflows/import-smoke-on-ubuntu-py3-12.yml"><img src="https://img.shields.io/github/actions/workflow/status/scitex-ai/scitex-dev/import-smoke-on-ubuntu-py3-12.yml?branch=develop&label=Install-Check" alt="Install-Check"></a>
  <a href="https://github.com/scitex-ai/scitex-dev/actions/workflows/scitex-dev-quality-audit-on-ubuntu-latest.yml"><img src="https://img.shields.io/github/actions/workflow/status/scitex-ai/scitex-dev/scitex-dev-quality-audit-on-ubuntu-latest.yml?branch=develop&label=Quality" alt="Quality"></a>
  <a href="https://codecov.io/gh/scitex-ai/scitex-dev"><img src="https://img.shields.io/codecov/c/github/scitex-ai/scitex-dev/develop?label=CodeCov" alt="CodeCov"></a>
</p>
<!-- scitex-badges:end -->

---

## Problem and Solution

| # | Problem | Solution |
|---|---------|----------|
| 1 | **~70 ecosystem packages drift apart** -- versions, READMEs, sphinx setups, CLI conventions diverge faster than humans can audit | **`scitex-dev ecosystem audit-*`** -- `audit-project`, `audit-cli`, `audit-mcp-tools`, `audit-python-apis`, `audit-skills`, `audit-summary` enforce ~130 numbered rules across the whole ecosystem |
| 2 | **Skills scattered across ~70 source repos** -- AI agents can't discover them; humans can't review them | **`scitex-dev dev skills list / get / install`** -- discover installed leaf skills, install them into `~/.scitex/dev/skills/`, and optionally project them into Claude Code with `--claude-symlink` |
| 3 | **Coordinated releases need ten manual steps** -- bump version, push tag, watch CI, verify PyPI, deploy — done per-package, multiplied by 70 | **`scitex-dev ecosystem sync` + `validate-versions` + `gui open`** -- one-shot install/sync across hosts, version-mismatch detection, and a web dashboard with the live state |
| 4 | **Bulk renames across 70 repos break cross-references** -- import paths, doc references, symlinks — `sed -i` corrupts something every time | **`scitex-dev rename-symbols`** -- atomic rename with cross-reference updates, regex support, dry-run preview, git-safety guards |
| 5 | **Lint rules drift from the API they enforce** -- a renamed function in figrecipe leaves the rule pointing at a nonexistent symbol, and the bug only shows up months later | **`scitex-dev linter`** (engine, formerly `scitex-linter`) -- aggregates per-package rule plugins via the `scitex_dev.linter.plugins` entry point. Rules ship in the package whose API they enforce, so rename + rule + test land in one PR. Doc-block linting for `.py` / `.ipynb` / `.md` / `.rst`. `scitex-dev linter sweep` walks every package's README + docs in one shot |

## Installation

There are exactly two installs. The CLI, the MCP server, icon rendering
and skills all ship in the base install — there is no per-feature menu to
assemble, and nothing to forget to add.

```bash
# Everything you need to USE scitex-dev:
pip install scitex-dev

# Plus the maintainer toolchain (pytest, sphinx, ...) — for working ON it:
pip install scitex-dev[all]
```

`[all]` adds development and documentation tooling and optional integrations,
including the Flask dashboard and NumPy diagnostics, on top of the base install. Extra names are restricted to
`{all, dev, docs}` by PS-225, because a per-feature extra is something
somebody eventually pins — and a pin naming an extra that does not exist
installs anyway, warns into a log nobody reads, and silently omits the
capability.

### Configuration

Copy [`.env.example`](.env.example) to `.env` (gitignored) at your
project root, then edit. CLI flags always override env vars. The full
list (with inline comments) lives in `.env.example`.

<details>
<summary><strong>Local state directories</strong></summary>

<br>

scitex-dev reads optional config + cache from the canonical SciTeX
local-state locations:

| Path                          | Scope         | Purpose                              |
|-------------------------------|---------------|--------------------------------------|
| `~/.scitex/dev/`              | user-global   | per-user config, cache               |
| `<proj-root>/.scitex/dev/`    | project-local | overrides for the current repo       |

Project-local wins when both exist. Both are optional.

</details>

## Architecture

```
scitex_dev/
├── _cli/
│   ├── audit/                ← rule corpus (PA*, PS*, SK*, §*)
│   │   ├── _api/             ← Python-API rules (PA-1xx)
│   │   ├── _project/         ← project-structure rules (PS-1xx, PS-5xx)
│   │   ├── _skills/          ← skill-file rules (SK-1xx)
│   │   └── _summary/         ← CLI/MCP §-rules + audit-all wrapper
│   ├── ecosystem/            ← cross-package commands (audit-all, list, …)
│   └── skills/               ← `scitex-dev dev skills` implementation
├── _ecosystem/               ← shared helpers (skill-quality, ECOSYSTEM map)
├── _skills/                  ← canonical skill-file corpus shipped to agents
└── testing/                  ← `audit_all_for_package` pytest helper
```

Audit rules live alongside the code they check. Each rule has a
docstring, an entry in `RULES`, a severity in `_SEVERITY_OVERRIDES`,
and at least one unit test under `tests/.../_audit/_project/`.

## Demo

```mermaid
flowchart LR
    A["scitex-dev ecosystem<br/>audit-all <pkg>"] --> B[audit-cli]
    A --> C[audit-mcp-tools]
    A --> D[audit-skills]
    A --> E[audit-python-apis]
    A --> F[audit-project]
    B & C & D & E & F --> G{any error?}
    G -- "yes" --> H["exit 1<br/>(CI fails)"]
    G -- "no" --> I["exit 0<br/>(CI green)"]
```

`scitex-dev` is a CLI/audit tool — its "demo" is the audit running on a
package. Sample output (run on `scitex-io`):

```
=== audit-cli ===
ok    scitex-io: no CLI convention violations

=== audit-mcp-tools ===
ok  scitex-io: no MCP convention violations

=== audit-skills ===
ok  scitex-io: no skills violations

=== audit-python-apis ===
ok  scitex-io: no Python API violations

=== audit-project ===
ok  scitex-io: no project-structure violations
```

Failure mode (sample, scitex-dsp before the Hilbert fix):

```
=== audit-project ===
fail  scitex-dsp (/home/ywatanabe/proj/scitex-dsp): 2 error(s)
  [E] [PS-141 §1] README.md: missing mandatory `## Demo` section
  [E] [PS-503 §5] examples/01_demo_out: no FINISHED_SUCCESS/<session_id>/ subdir
```

See [`examples/`](examples/) for runnable demos that exercise
`scitex-dev`'s own commands (search, version-management, docs
aggregation).

## Selective discovery and context accounting

`scitex-dev context measure --input selected-snapshot.json --json` measures
caller-selected advertised MCP definitions and skill headers. The same pure
API is `scitex_dev.measure_context` and the MCP tool is `dev_context_measure`.
`configure_mcp_discovery` reuses FastMCP search after host policy; no custom
search engine or tokenizer is introduced. Reports show JSON bytes/code points,
explicit owner attribution and unknown client context, without echoing tool
descriptions. See [scope, schema and client limits](docs/context-discovery.md).
The umbrella route is `scitex dev context measure` when Dev is installed.

## Five Interfaces

<details>
<summary><strong>Python API ⭐⭐</strong></summary>

Version, CI, documentation and error-handling helpers are re-exported from
`scitex_dev` (internals live under `_release`, `_docs`, `_core`; don't import
those paths). The active-project selector lives in `scitex_dev.project`.

```python
# Discover installed versions and documentation
from scitex_dev import list_versions, get_docs, search
versions = list_versions()
get_docs(package="scitex-writer")
search("save figure")

# Preview changes; applying a plan is a separate action
from scitex_dev import fix_local, preview_rename
fix_local(packages=["scitex-stats"], confirm=False)
preview_rename(pattern="old_name", replacement="new_name", directory=".")

# LLM-friendly types
from scitex_dev import Result, ErrorCode, supports_return_as

# Active project (scitex-dev >=0.62.0)
from scitex_dev.project import resolve_project
resolve_project(explicit="synthetic/owned")
```

> Discover and install skills through `scitex-dev dev skills list/get/install`.
> Python discovery/export helpers are public in `scitex_dev.ecosystem`:
> `list_skills`, `get_skill` and `export_skills`; the root module does not
> re-export them.

</details>

<details open>
<summary><strong>CLI Commands ⭐⭐⭐ (primary)</strong></summary>

```bash
# Ecosystem management
scitex-dev ecosystem list
scitex-dev ecosystem list --versions
scitex-dev ecosystem validate-versions --dry-run

# Active project (scitex-dev >=0.62.0)
scitex-dev project use synthetic/owned
scitex-dev project get --json
scitex-dev project clear

# Documentation
scitex-dev docs get
scitex-dev docs search "save figure"

# Bulk rename
scitex-dev rename-symbols old_name new_name --dry-run

# See all commands
scitex-dev --help
scitex-dev --help-recursive
```

Project references are `owner/name` or `all`. Resolution checks an explicit
Python argument first, then `SCITEX_PROJECT`, then the persisted selection
under `$SCITEX_DIR/scitex-dev/active_project` (default
`~/.scitex/scitex-dev/active_project`). `project current` remains a deprecated
alias for `project get`; its warning goes to stderr so JSON stays usable.
Selecting a project does not authorize access to it or establish store
tenancy.

</details>

<details>
<summary><strong>MCP Server ⭐⭐</strong></summary>

```bash
# Start server
scitex-dev mcp start

# Check setup
scitex-dev mcp doctor
scitex-dev mcp list-tools

# Installation info
scitex-dev mcp install
```

**Claude Code setup** — add `.mcp.json` to your project root. The executable
must be available in the client environment; configure supported variables in
that environment rather than relying on an undocumented `.src` loader.

```json
{
  "mcpServers": {
    "scitex-dev": {
      "command": "scitex-dev",
      "args": ["mcp", "start"]
    }
  }
}
```

</details>

<details open>
<summary><strong>Skills ⭐⭐⭐ (primary)</strong></summary>

<br>

Skills provide workflow-oriented guides that AI agents query to discover capabilities and usage patterns.

```bash
scitex-dev dev skills list --package scitex-dev --json
scitex-dev dev skills get scitex-dev SKILL
scitex-dev dev skills install --package scitex-dev --claude-symlink --dry-run --json
# Review the plan; omit --dry-run to install. Use --link for editable sources.
```

> **[Full skills directory](https://github.com/scitex-ai/scitex-dev/tree/develop/src/scitex_dev/_skills)**

| Skill | Content |
|-------|---------|
| `result-types` | `Result`, `ErrorCode`, `@supports_return_as` for LLM-friendly responses |
| `cli-mcp-utils` | CLI and MCP utility helpers |
| `config` | Package configuration and priority config patterns |
| `versions` | Version management, mismatch detection and fixing |
| `ecosystem` | Ecosystem list, sync, and commit workflows |
| `rename` | Safe bulk rename with cross-reference updates |
| `docs-search` | Documentation aggregation and unified search |
| `test-runner` | Local and HPC test execution |
| `full-update` / `full-update-deploy` | End-to-end audit → bump → release → sync pipelines |
| `agentic-test-overview` / `-skills` / `-mcp` | Agent-vs-agent quality testing |
| `dynamic-audit` | Cross-package periodic audit checklist |
| `env-vars` | `SCITEX_DEV_*` / `SCITEX_*` environment variable reference |

</details>

<details>
<summary><strong>Web API: leaf contracts, SDK validation, explicit host admission</strong></summary>

scitex-dev dispatches leaf-owned rules and hooks; scitex-sdk owns the Web API
contract. This is not a claim that scitex-dev's legacy Flask dashboard is a
complete public Web API. A missing interface needs an implementation or an
explicit, justified exception.

See [the five-interface audit workflow](src/scitex_dev/_skills/scitex-dev/39_interface-audit.md)
for discovery commands, source evidence and coverage limits. The legacy
`deploy_scitex_hub` helper targets an older deployment layout; use Hub-owned
release and deployment procedures for current services.

</details>

## Part of SciTeX

`scitex-dev` is part of [**SciTeX**](https://scitex.ai). Install via
the umbrella with `pip install scitex[dev]` to use as
`scitex.dev` (Python) or `scitex dev ...` (CLI).

SciTeX follows the Four Freedoms for Research below, inspired by
[the Free Software Definition](https://www.gnu.org/philosophy/free-sw.en.html):

>Four Freedoms for Research
>
>0. The freedom to **run** your research anywhere — your machine, your terms.
>1. The freedom to **study** how every step works — from raw data to final manuscript.
>2. The freedom to **redistribute** your workflows, not just your papers.
>3. The freedom to **modify** any module and share improvements with the community.
>
>AGPL-3.0 — because we believe research infrastructure deserves the same freedoms as the software it runs on.

---

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40">
  </a>
</p>


### Federated executable hooks

Leaves register `scitex_dev.hooks` providers and own their `HookRule.check`
implementations. scitex-dev discovers and dispatches these checks without
embedding a package's output, container, or credential policy.

```bash
scitex-dev dev hooks install --provider scitex-logging --harness claude --config .claude/settings.local.json --dry-run
```

Omit `--dry-run` to merge the provider's bindings into native configuration.
Hermes uses `--harness hermes --config <profile>/config.yaml` and its own atomic
writer, so run installation where Hermes is available. Use `--python` when the
target's interpreter differs from the installer. Other settings/providers are
preserved; repeating installation does not duplicate bindings. Native commands
call `python -m scitex_dev.hooks.dispatch --provider <distribution>` with the
harness JSON payload on stdin. A missing provider or failing check refuses
verification with exit code 2. Post-tool checks report after the operation;
only pre-tool events can prevent that operation. Harness approval is separate
from installation and is never silently granted by this installer.
