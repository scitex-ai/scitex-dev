---
description: |
  [TOPIC] Readme Organization
  [DETAILS] Canonical README.md template for every SciTeX package — required section order (one-liner → install → quickstart → interfaces → status/CI badges → links → licence → Four-Freedoms footer), badge set (PyPI version, CI, coverage, RTD, licence), collapsible blocks for long examples, `import scitex` (never `as stx`) in all snippets, absence of the ywatanabe@ signature, and the intra-README link contract that external RTD/Sphinx builds depend on. Use when scaffolding a new repo's README or auditing one for ecosystem drift.
tags: [scitex-general-docs-readme]
---

# README Organization (SciTeX)

## Reference package

When in doubt about any rule on this page, mirror
[**scitex-io**](https://github.com/ywatanabe1989/scitex-io/blob/develop/README.md).
It is the canonical example of every convention here — badge layout,
section ordering, blockquote callouts, mermaid sizing, `<details>`
collapsing, Problem/Solution cell length, hook integration recipe.

## Detailed guidance (sibling leaves)

- [06_readme-section-order.md](06_readme-section-order.md) — Standard Section Order: the canonical top-to-bottom README structure
- [07_readme-presentation-conventions.md](07_readme-presentation-conventions.md) — Presentation conventions (adopted 2026-05): Quick Start, Installation one-liner, How-it-works, callouts, badge row (PS-167), interface ratings
- [08_readme-badges-interfaces-footer.md](08_readme-badges-interfaces-footer.md) — Badge Row, collapsible Interface sections + deep-link patterns, and the Four Freedoms Footer
- [09_readme-examples-header.md](09_readme-examples-header.md) — Project README.md Examples: Header, Problem and Solution, Installation
- [10_readme-examples-quickstart.md](10_readme-examples-quickstart.md) — Project README.md Examples: Quick Start and Footer

## SciTeX-Specific Rules

- **No `ywatanabe@scitex.ai`** in footer — community project (audit: **PS-111**)
- **`import scitex`** and **`import scitex as stx`** are both acceptable
  in code blocks; pick one and stay consistent within a single README.
  (Reality: the umbrella canonical README and most skill docs use `as stx`;
  earlier guidance forbidding `as stx` was inconsistent with practice.)
- **Verify all format/feature claims** against actual `_builtin_handlers.py` or source code
- **Match quickstart.rst** — README Quickstart and Sphinx quickstart should show the same examples
- **Add Logo and Icon** — either `docs/assets/images/{scitex-logo-blue-cropped.png,scitex-icon-navy-inverted.png}`
  or `docs/{scitex-logo-blue-cropped.png,scitex-icon-navy-inverted.png}`
  is accepted (audit: **PS-112** for the top logo).

## Canonical Template + Audit Rules

The literal canonical README lives at
[`04_docs/01_readme_template.md`](01_readme_template.md).
Run `scitex-dev ecosystem audit-project <pkg>` to check a repo against
the template. The following warn-only rules enforce its load-bearing
sections:

| Code  | Enforces                                                            |
|-------|---------------------------------------------------------------------|
| PS-106 | Coverage badge in the first ~4 KB                                   |
| PS-107 | Required H2 sections: `## Installation`, `## Quick Start`, `## Part of SciTeX` |
| PS-109 | PyPI version badge in the first ~4 KB                               |
| PS-110 | Four Freedoms for Research blockquote present                       |
| PS-111 | Banned personal email `ywatanabe@scitex.ai` absent                  |
| PS-112 | SciTeX logo image in the first ~4 KB                                |
