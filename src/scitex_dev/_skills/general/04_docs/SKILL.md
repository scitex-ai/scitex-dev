---
description: |
  [TOPIC] Documentation Surfaces
  [DETAILS] How a `scitex-*` package becomes understandable — the standard README template with required sections, badges, and footer; Sphinx docs (`conf.py`, troubleshooting); Read the Docs onboarding (`.readthedocs.yaml`, build config); env-vars-and-state documentation; and robust docs-CI that keeps `sphinx-build -W` strict while defending the four benign failure modes (docstring reST noise, GH006 commit-back, missing-peer autodoc, math). Use when writing or auditing a package's README, Sphinx tree, or docs CI.
tags: [scitex-general-docs-index]
---

# Documentation (SciTeX) — Index

How does *this* package become understandable? Audience: package authors.
Builds on the package layout ([../02_package/SKILL.md](../02_package/SKILL.md)).

## Sections

1. [01_readme.md](01_readme.md) — Standard README template, sections, badges, footer (router)
2. [06_readme-section-order.md](06_readme-section-order.md) — Standard Section Order for a package README
3. [07_readme-presentation-conventions.md](07_readme-presentation-conventions.md) — Presentation conventions (2026-05): Quick Start, badges (PS-167), interface ratings
4. [08_readme-badges-interfaces-footer.md](08_readme-badges-interfaces-footer.md) — Badge Row, Interface sections + deep-links, Four Freedoms Footer
5. [09_readme-examples-header.md](09_readme-examples-header.md) — README examples: Header, Problem and Solution, Installation
6. [10_readme-examples-quickstart.md](10_readme-examples-quickstart.md) — README examples: Quick Start and Footer
7. [01_readme_template.md](01_readme_template.md) — Copy-paste README skeleton
8. [02_sphinx.md](02_sphinx.md) — Sphinx docs, conf.py, troubleshooting
9. [11_sphinx-wheel-bundling.md](11_sphinx-wheel-bundling.md) — Bundling pre-built Sphinx HTML in the wheel (production serving)
10. [03_env-vars-and-state.md](03_env-vars-and-state.md) — Documenting env vars + local state surfaces
11. [03_rtd.md](03_rtd.md) — Read the Docs onboarding, `.readthedocs.yaml`, build config
12. [04_robust-ci.md](04_robust-ci.md) — Robust docs-CI: keep `sphinx-build -W` strict while defending the 4 benign failure modes
13. [05_adr.md](05_adr.md) — Architecture Decision Records: what an ADR is, when to write one, where it lives, and the copy/paste template
