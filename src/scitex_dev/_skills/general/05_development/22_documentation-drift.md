---
description: |
  [TOPIC] Documentation drift
  [DETAILS] Check README, agent instructions, skills, reference docs and examples
  against declared source and behavioral evidence. Use for impacted PR checks,
  daily agent reviews and release qualification. Distinguish scoped static
  checks, intended contracts, observed behavior and generated-artifact delivery;
  unavailable or manual evidence is not a pass. Reuse leaf-owned checks and
  Dev dispatch rather than maintaining another ecosystem inventory.
tags: [scitex-general-development-documentation-drift]
---

# Documentation drift

Documentation can disagree with source, the installed distribution or the
artifact actually served. Record which of these was checked. Source describes
observed behavior; an intended contract may reveal a code bug. Do not rewrite
an intended contract merely to match a broken implementation.

## Evidence near the claim

Cover `README.md`, existing `AGENTS.md`/`CLAUDE.md`, shipped skills, docstrings,
CLI/MCP descriptions, reference pages and examples when relevant. Keep agent
instructions linked to their authoritative skill instead of copying its body.
For a checkable claim, name the owning source symbol/file and its existing test
or other evidence beside the claim or in the leaf's normal test documentation.
A source link alone does not establish correctness.

Use the leaf's real tests to exercise documented behavior in owned temporary
fixtures: expected values/schema, error cases and observable side effects.
Compilation, import success, a passing link check or Sphinx build is not a
behavior assertion. Never discover and execute arbitrary documentation fences;
network, models, messages, installers and live data require their own authorized
fixtures. If no safe executable check exists, report manual/unverified scope.

## Select checks by cadence

- **PR:** follow the changed source's declared documentation references and
  public callers; check the affected claims and corresponding leaf-owned tests.
  Include agent instructions and skill references, not only edited Markdown.
- **Daily:** one authorized agent job on a selected host reviews the current
  source/environment and reports drift plus unchecked scope. Advance a repo's
  successful-review checkpoint only after its selected coverage completes;
  preserve partial/failed attempts and the changes still needing review. Discover installed declarations and available tools in that environment;
  do not maintain a second package list or enable every federated job. Preserve
  previous evidence and identify source SHAs, versions and actual commands.
- **Release:** broaden to the shipped wheel/sdist, installed help/metadata,
  packaged skills and generated docs. Verify their source/version binding and
  applicable behavioral controls; check the actually served artifact separately.

A daily schedule is not evidence that the first review ran. Follow the job's
explicit scope; cadence does not authorize package installs, publication or
service changes. Use the existing scheduler or `scitex_dev.jobs` federation when
appropriate; creating this check does not require a new scheduling framework.

## Existing tools and their limits

Available in **public Dev 0.62.15**:

```python
from pathlib import Path
from scitex_dev import verify_docs_and_skills

report = verify_docs_and_skills(
    Path("."), documents=[Path("README.md")]
)
print(report["status"], report["checked_scope"], report["unverified"])
```

This is a read-only static check of closed Markdown Python/py fences and local
src-layout imports/direct definitions. Explicit `documents` can select existing
agent Markdown or guides. Defaults cover README and source skills. It does not
execute examples, check signatures/results, validate prose or other interfaces,
or compare installed/exported skills. Inspect `limitations`; `ok` is scoped,
`incomplete` is not a complete pass, and `needs_update` reports a detected issue.

The CLI wrapper was added alongside this skill update; older installs,
including 0.62.15, lack this route. Check `scitex dev docs --help` (or
`scitex-dev docs --help`) before using it: a source checkout alone does not
establish installed availability. Prefer the umbrella route when available;
standalone `scitex-dev` is the bootstrap route:

```bash
scitex dev docs validate --path /owned/package --document README.md --json
scitex-dev docs validate --path /owned/package --document AGENTS.md --json
```

It calls that same helper. Exit codes: 0 = scoped `ok`, 1 = `needs_update`,
2 = `incomplete`. It never turns missing/manual evidence into success.

Existing broader checks remain separate:

```bash
scitex dev ecosystem audit-all PACKAGE --path /owned/package
scitex dev ecosystem audit-skills PACKAGE --path /owned/package
scitex dev docs list-providers --json
```

Audit rules check their declared scope, not all prose semantics. Provider rows
are metadata declarations, not proof of callable/live interfaces. Cached-skill
version warnings are not byte/content checks or proof of agent discovery.
Prefer the owning leaf's audit/test primitives; Dev dispatches them. SDK owns
Web contract validation ports, leaves own endpoint semantics, and the host owns
rendering/admission. A registered GUI, HTTP 200 or docs link proves none of those
other contracts by itself.

## Generated documents still need evidence

Generate repetitive reference material from qualified source where practical,
but retain the source identity, generator/config inputs and output binding.
Generation can use the wrong installed package, miss a page, reuse stale output
or faithfully document a bug. A successful build does not prove content valid,
and an exact bundle does not prove the live host serves it. Report those checks
separately; fix the owning source/generator or document a genuine limitation.

Report each outcome as verified-with-scope, drift/failure, unverified/manual or
not-applicable-with-reason. Never flatten a skip, unavailable tool, failed read
or unexecuted check into a green ecosystem summary.
