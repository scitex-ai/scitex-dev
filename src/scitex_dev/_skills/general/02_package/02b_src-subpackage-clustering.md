---
description: |
  [TOPIC] Package Src — subpackage clustering decision rules
  [DETAILS] How to organize a growing `src/<pkg>/` into subpackages. The logical-categorization decision rules (group by responsibility not blind prefix-promotion, use the public-API surface as the taxonomy, leave singletons flat, cross-cluster helpers go up one level, prefer fewer larger dirs), a worked wrong-way/right-way example on scitex-dev's `_cli_*`, and the PS-108b topical-cluster rule for many flat files that share a topic but no prefix. Companion to [02_project-structure-src.md](02_project-structure-src.md).
tags: [scitex-general-package-project-structure-src]
---

# `src/<pkg>/` — subpackage clustering

> Parent leaf: [`./src`](02_project-structure-src.md) — see its "Subpackage clusters — keep `src/<pkg>/` navigable" section (PS-108) for when to promote a prefix cluster into a subpackage. This leaf carries the detailed decision rules.

### Logical categorization, not blind prefix-promotion

The prefix is a *trigger* for noticing a cluster, not a *recipe* for
the new layout. When PS-108 fires, resist the temptation to mechanically
move every `<prefix>_*.py` into `_<prefix>/` and stop. Two files with
the same prefix can belong to two different responsibilities, and two
files with different prefixes can belong together.

Decision rules, in order:

1. **Group by what callers ask of these files, not by their leaf name.**
   If `mcp.py`, `mcp_utils.py`, `_mcp_compat.py`, `_mcp_server.py` all
   serve "the MCP integration", they belong in `_mcp/`. If among those
   one file is actually only there for *agentic-test* harness code,
   that file goes in `_agentic_testing/` regardless of its name.
2. **Use the public-API surface as the taxonomy.** If `<pkg> --help`
   already groups commands (Ecosystem / Development / Documentation /
   Interface / Shell), mirror that taxonomy in the source layout. One
   subpackage per category is a strong default — the CLI grouping was
   already designed by humans for humans, so reusing it is free
   discoverability.
3. **A single file with no peers does not need a directory.** PS-108
   threshold is 3 for a reason: 1–2 files are findable as flat siblings.
   Don't create a `_logging/` package for one `logging.py`.
4. **Cross-cluster shared helpers go up one level, not into either cluster.**
   If `_mcp/` and `_cli/` both import a `_dispatch_table` helper, keep
   that helper as a flat sibling at `src/<pkg>/_dispatch.py` rather than
   picking a "primary" subpackage to host it. PS-108 won't flag a single
   file.
5. **When unsure, prefer fewer larger directories over many small ones.**
   You can split later (cheap) but un-splitting is messy (every external
   caller has the deeper path memorized).

A worked example — the **wrong** way to refactor scitex-dev's `_cli_*`:

```
src/scitex_dev/_cli/
├── _audit.py
├── _audit_api.py
├── _audit_project.py
├── _audit_skills.py
├── _completion.py
├── _doctor.py
├── _ecosystem.py
├── _quality.py
├── _quality_frontmatter.py
├── _skills.py
├── _skills_tags.py
└── _stats.py
```

That's just the prefix moved one level deeper. Twelve siblings in one
flat dir is the same smell at a different depth.

The **right** way — group by what each command actually does:

```
src/scitex_dev/_cli/
├── __init__.py            # root group + register_*  helpers
├── _root.py               # main(), version flag, --help-recursive
├── audit/                 # everything that *audits*
│   ├── __init__.py
│   ├── _project.py        # was _cli_audit_project.py glue
│   ├── _api.py            # was _cli_audit_api.py glue
│   ├── _skills.py         # was _cli_audit_skills.py glue
│   └── _summary.py        # was _cli_audit.py (cross-cutting)
├── ecosystem/             # `<pkg> ecosystem ...` commands
│   ├── __init__.py
│   └── _registry.py       # was _cli_ecosystem.py
├── quality/               # quality / linting commands
│   ├── __init__.py
│   ├── _check.py
│   └── _frontmatter.py
├── skills/                # skill-management commands
│   ├── __init__.py
│   ├── _manage.py
│   └── _tags.py
├── _completion.py         # one file — leave flat
├── _doctor.py             # one file — leave flat
└── _stats.py              # one file — leave flat
```

The new tree mirrors the CLI's own `--help` categories (Ecosystem /
Development / Documentation / Interface / Shell) plus an `audit/`
group that didn't exist as a CLI category but obviously *should* —
the refactor surfaces a missing piece of the public taxonomy too.
**That's the test** for whether your grouping is right: it should
reveal something true about the package's structure, not just shuffle
files into shorter siblings.

## Topical clusters with no shared prefix — the silent mess

PS-108 catches prefix clusters (`_cli_*`, `_skills_*`). It does **not**
catch the second mess pattern: a package root with many flat files that
*share a topic* but no prefix.

Example — scitex-dev's actual `src/scitex_dev/` had ~30 flat top-level
files like `ci.py`, `deploy.py`, `github.py`, `rtd.py`,
`_version_fixer.py`, `_release_publisher.py`, `versions.py` — clearly a
"release/CI" cluster, but no shared prefix means PS-108 stays silent.

**Rule (PS-108b — pending audit)**: when `src/<pkg>/` (or any
subpackage) holds **>15 flat `.py` files** excluding `__init__.py` and
`__main__.py`, group them into topical subpackages. Use the same
decision rules as the prefix case (group by responsibility, mirror the
public taxonomy, leave singletons flat).

Suggested categories every package tends to need (rename to taste):

| Category | Examples of files that belong here |
| -------- | ---------------------------------- |
| `_release/` | CI helpers, deploy, github, rtd, version bumpers |
| `_docs/`    | docs build, search, sphinx hooks |
| `_core/`    | config, errors, types, dist-info, imports, decorators |
| `_quality/` | linters, audit-core (NOT the CLI surface — that lives in `_cli/audit/`) |

Single-file orphans (no peers) **stay flat** — see decision rule #3
above. Don't create `_logging/` for one `logging.py`.
