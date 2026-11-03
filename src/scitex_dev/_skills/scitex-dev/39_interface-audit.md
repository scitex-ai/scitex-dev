---
description: |
  [TOPIC] Five-interface audit
  [DETAILS] Audit Python, CLI, MCP, Web API and skills against requested source, installed metadata and actual execution coverage.
tags: [scitex-dev-interface-audit]
---

# Five-interface audit

Use this workflow when checking agent usability or documentation drift across
packages. Python owns business logic; CLI, MCP and Web adapters delegate to it.
Leaves own capability contracts, rules and skills. scitex-dev dispatches them;
scitex-sdk owns the Web API contract and host integration primitives.

## Discover without executing operations

```bash
scitex-dev --help-recursive
scitex-dev list-python-apis --json
scitex-dev mcp list-tools --json
scitex-dev docs get
scitex-dev docs search "interfaces" --json
scitex-dev dev skills list --package scitex-dev --json
scitex-dev dev skills get scitex-dev SKILL
scitex-dev dev skills install --package scitex-dev --claude-symlink --dry-run --json
```

Use each leaf's actual `--help` for its Python/MCP catalog commands. Leaf CLI
paths and catalog JSON envelopes are not yet identical. The central
`dev skills list --package <distribution> --json` route discovers registered
installed skills even when a leaf has no `dev skills` subgroup. Installation
uses `~/.scitex/dev/skills/`; the optional Claude projection makes that store
visible to that harness. A dry run does not install or prove client discovery.

## Inspect the requested checkout

From its root, substitute its distribution name for `scitex-dev`:

```bash
scitex-dev ecosystem audit-python-apis scitex-dev --path . --json
scitex-dev ecosystem audit-cli scitex-dev --path . --json
scitex-dev ecosystem audit-mcp-tools scitex-dev --path . --json
scitex-dev ecosystem audit-skills scitex-dev --path . --json
scitex-dev ecosystem audit-project scitex-dev --path . --json
```

Record the checkout commit, imported/installed versions and rule-provider
metadata separately. Python source auditing must inspect the resolved checkout,
not substitute a different installed copy. Missing source is not auditable.
An absent MCP server, empty tool list or placeholder handler is missing coverage
or implementation, even if a discovery command exits zero. A symbol count does
not prove that those symbols are intended public capabilities or callable.

For Web APIs, read the SDK-owned `scitex-app/24_web-api-contract.md` skill from
an SDK installation that actually contains it. Its `scitex_dev.audit.project`
provider contributes `PS-SDK-WEB`, and its `scitex_dev.hooks` provider contributes
Web contract checks. Check entry-point metadata: newer checkout code does not
prove an older wheel supplies the provider. The targeted command is:

```bash
scitex-dev ecosystem audit-project scitex-dev --path . --rule PS-SDK-WEB --json
```

Use the leaf under review, not this example target, for its declarations.
The check parses inert descriptors and owned handler bindings; passing it does
not mount routes, enable hooks or verify live authorization/availability.

## Report evidence and gaps

For each interface record source implementation, installed discovery, host
admission/enablement and live execution separately, including untested states.
Five interfaces are the default target; document an explicit reason where one
is inapplicable. An unimplemented interface is not an exception by default.

Validate documented imports and signatures against the same source revision.
Check help/JSON discovery without invoking destructive operations. Use owned
fixtures for meaningful execution tests; never infer success from `--help`, a
catalog or a static audit alone. Report audited files/providers and skipped
coverage instead of calling a partial check an ecosystem-wide pass.
