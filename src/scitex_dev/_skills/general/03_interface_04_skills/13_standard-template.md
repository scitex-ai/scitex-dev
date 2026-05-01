---
name: skills-standard-template
description: The scaffold template every new SciTeX package should start from — full SKILL.md + the standard-5 leaf set (01_quick-start, 02_python-api, 03_cli-reference, 04_mcp-tools, 20_env-vars) with placeholders. Lives at `~/proj/scitex-dev/src/scitex_dev/_skills_template/<pip-name>/`; cloned by `scitex-dev skills init --package <name>`.
tags: [scitex-python, scitex-general, scitex-package, meta]
---

# Standard `_skills/<pip-name>/` Scaffold

## How to scaffold

```bash
scitex-dev skills init --package my-package [--dest src/my_package/_skills/]
```

This clones the template at `~/proj/scitex-dev/src/scitex_dev/_skills_template/<pip-name>/` into the destination, substituting `<pip-name>` and `<import-name>` placeholders.

> **Status:** the `skills init` CLI is planned (see [TODO.md](TODO.md)). Until shipped, copy the templates below by hand.

## Files created

```
src/<import_name>/_skills/<pip-name>/
  SKILL.md                  # index
  01_quick-start.md         # 30-second tour
  02_python-api.md          # Python API surface
  03_cli-reference.md       # CLI subcommands
  04_mcp-tools.md           # MCP tool catalog
  20_env-vars.md            # SCITEX_<MODULE>_* environment variables
```

Add 10–19 leaves (one per workflow) and 20+ leaves (one per meta topic) as the package grows.

## Template — `SKILL.md`

```markdown
---
name: <pip-name>
description: <one-line summary of what the package does and when to use it>.
tags: [<pip-name>, scitex-package]
allowed-tools: mcp__scitex__<module>_*
primary_interface: <python|cli|mcp|skills|hook|mixed>
interfaces:
  python: <0-3>
  cli: <0-3>
  mcp: <0-3>
  skills: <0-3>
  hook: 0
  http: 0
---

# <pip-name>

<one-paragraph intro>

> **Convention (since 2026-05):** the old single-line
> `> **Interfaces:** Python ⭐⭐⭐ · CLI ⭐ · ...` callout is deprecated.
> Put the star rating directly on each interface section header below
> (e.g. `## Python API ⭐⭐⭐`). Strip parenthetical expansions
> (`(Application Programming Interface)`) and trailing descriptors
> (`-- for AI Agents`, `— for AI Agent Discovery`) — the bullets carry
> meaning, the prose doesn't.

## Installation & import

\`\`\`bash
pip install <pip-name>
\`\`\`

\`\`\`python
import <import_name>
\`\`\`

## Sub-skills

### Core (01–09)
- [01_quick-start.md](01_quick-start.md) — 30-second tour
- [02_python-api.md](02_python-api.md) — Python API surface
- [03_cli-reference.md](03_cli-reference.md) — CLI subcommands
- [04_mcp-tools.md](04_mcp-tools.md) — MCP tool catalog

### Meta (20+)
- [20_env-vars.md](20_env-vars.md) — Environment variables
```

## Template — `01_quick-start.md`

```markdown
---
name: quick-start
description: 30-second tour of <pip-name> — install, import, smallest useful example.
tags: [<pip-name>, scitex-package]
---

# Quick Start

## Install

\`\`\`bash
pip install <pip-name>
\`\`\`

## Smallest useful example

\`\`\`python
import <import_name>

# <one example that demonstrates the primary use case>
\`\`\`

## Next

- [02_python-api.md](02_python-api.md) — full API
- [03_cli-reference.md](03_cli-reference.md) — CLI usage
```

## Template — `02_python-api.md`

```markdown
---
name: python-api
description: Public Python API of <pip-name> — exported functions, signatures, return types.
tags: [<pip-name>, scitex-package]
---

# Python API

## Exports

\`\`\`python
from <import_name> import <fn_a>, <fn_b>, ...
\`\`\`

## <fn_a>

\`\`\`python
def <fn_a>(arg1, arg2=default) -> ReturnType:
    """One-line summary."""
\`\`\`

[Real example, expected output, edge cases.]

## <fn_b>

[Same shape.]
```

## Template — `03_cli-reference.md`

```markdown
---
name: cli-reference
description: <pip-name> CLI subcommands — noun-verb structure with universal flags.
tags: [<pip-name>, scitex-package]
---

# CLI Reference

\`\`\`bash
<pip-name> --help
\`\`\`

## Subcommands

| Command | Purpose |
|---|---|
| `<pip-name> <noun> <verb>` | <one-line> |
| `<pip-name> mcp start` | Launch MCP server |
| `<pip-name> mcp list-tools` | List MCP tools |
| `<pip-name> skills list` | List bundled skills |

See `general/03_interface_02_cli/` for the noun-verb convention.
```

## Template — `04_mcp-tools.md`

```markdown
---
name: mcp-tools
description: MCP tools registered by <pip-name> — agent-callable surface.
tags: [<pip-name>, scitex-package]
---

# MCP Tools

| Tool | Purpose |
|---|---|
| `<module>_<verb>_<noun>` | <one-line> |
| `<module>_skills_list` | List package skills |
| `<module>_skills_get` | Get a specific skill |

See `general/03_interface_03_mcp/` for the `<pkg>_<verb>_<noun>` naming rule.
```

## Template — `20_env-vars.md`

```markdown
---
name: env-vars
description: Environment variables read by <pip-name>. All use the `SCITEX_<MODULE>_*` prefix per ecosystem rule.
tags: [<pip-name>, scitex-package]
---

# Environment Variables

| Name | Default | Purpose |
|---|---|---|
| `SCITEX_<MODULE>_<NAME>` | `<default>` | <one-line> |

See `general/01_ecosystem_04_environment-variables.md` for the prefix rule.
```

## Cross-references

- [03_skill-md-as-index.md](03_skill-md-as-index.md) — why SKILL.md must stay index-only
- [04_numbered-prefix-convention.md](04_numbered-prefix-convention.md) — bucket meanings
- [05_frontmatter-metadata.md](05_frontmatter-metadata.md) — every frontmatter field explained
- [14_general-skills-inheritance.md](14_general-skills-inheritance.md) — how `general/` rules ship alongside this scaffold
