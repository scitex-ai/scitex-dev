---
description: |
  [TOPIC] README Badges, Interfaces & Footer
  [DETAILS] The SciTeX-style badge row, the collapsible interface sections (`## <N> Interfaces` with star ratings and canonical "Full X reference" deep-link patterns per interface), the planned `scitex-dev readme refresh` auto-generation, and the Four Freedoms footer block. Use when writing or auditing a README's badge row, interface `<details>` blocks, deep-links, or footer.
tags: [scitex-general-docs-readme]
---

# README Badges, Interfaces & Footer (SciTeX)

## Badge Row (SciTeX Style)

```markdown
<p align="center">
  <a href="https://badge.fury.io/py/PACKAGE"><img src="https://badge.fury.io/py/PACKAGE.svg" alt="PyPI version"></a>
  <a href="https://PACKAGE.readthedocs.io/"><img src="https://readthedocs.org/projects/PACKAGE/badge/?version=latest" alt="Documentation"></a>
  <a href="https://github.com/ywatanabe1989/PACKAGE/actions/workflows/ci.yml"><img src="https://github.com/ywatanabe1989/PACKAGE/actions/workflows/ci.yml/badge.svg" alt="Tests"></a>
  <a href="https://www.gnu.org/licenses/agpl-3.0"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License: AGPL-3.0"></a>
</p>
```

## Interface sections (collapsible)

The README's `## <N> Interfaces` section contains one `<details>` block
per interface. Star ratings live on the `<summary>` (not in a separate
callout); strip parenthetical expansions and `-- for AI Agents` /
`— for AI Agent Discovery` tails (audit rule **PS-118**).

**All blocks may be collapsed** (`<details>` without `open`). The
historical requirement to mark at least one as `<details open>` is no
longer enforced (audit rule **PS-131** relaxed). Optionally still mark
the primary as `<details open>` when its example doubles as a
quick-start and the package omits a top-level `## Quick Start`
section — but most packages now ship a top-level `## Quick Start`
that carries that role, so every interface block stays collapsed.

```markdown
<details>
<summary><strong>Python API ⭐⭐⭐</strong></summary>
[Minimal `import <pkg>` example, 3-10 lines]
> **[Full API reference](<deeplink>)**
</details>

<details>
<summary><strong>CLI Commands ⭐⭐</strong></summary>
[Minimal command examples]
> **[Full CLI reference](<deeplink>)** · run `<pkg> --help-recursive` for the live tree.
</details>

<details>
<summary><strong>MCP Server ⭐⭐</strong></summary>
[Tool table + `<pkg> mcp start`]
> **[Full MCP specification](<deeplink>)** · run `<pkg> mcp list-tools` for the live registry.
</details>

<details>
<summary><strong>Skills ⭐</strong></summary>
[Skill table + `<pkg> skills list`]
> **[Full skills directory](https://github.com/ywatanabe1989/<pkg>/tree/develop/src/<import>/_skills/<pkg>)**
</details>
```

Star ratings are **required** on every interface summary (PS-120) —
they signal which interface is the package's primary user surface.
Drop only the trailing parenthetical tags like
`— for AI Agents` / `— for AI Agent Discovery` (PS-118); keep the
stars.

> **Reference package: `scitex-io`** — the canonical example of every
> rule on this page. When in doubt, mirror its README structure, badge
> layout, section ordering, blockquote-callout style, mermaid sizing,
> `<details>` collapsing, and Problem/Solution cell length.

### Canonical "Full X reference" deep-link patterns

Each `Full X` link **must** be a deep-link, not a bare RTD root URL
(audit rule **PS-123**). The deep-link points into the bundled
`_sphinx_html/` (also surfaced via Read the Docs):

| Interface  | Canonical deep-link                                                          |
|------------|------------------------------------------------------------------------------|
| Python API | `https://<pkg>.readthedocs.io/en/latest/api/<import_name>.html`              |
| CLI        | `https://<pkg>.readthedocs.io/en/latest/quickstart.html` (or dedicated page) |
| MCP        | `https://<pkg>.readthedocs.io/en/latest/api/<import_name>._mcp.html`         |
| Skills     | `https://github.com/ywatanabe1989/<pkg>/tree/develop/src/<import>/_skills/<pkg>` |

Skills point at the source tree on GitHub (not RTD) because skill
markdown is consumed by AI agents that follow the directory structure
directly.

### Future: `scitex-dev readme refresh` (planned)

The interface block bodies (code examples + tool tables + skill tables)
should eventually be auto-generated between markers like
`<!-- scitex-api:start --> ... <!-- scitex-api:end -->`. The generator
will call `scitex_dev.introspect.api(<pkg>)`, `<pkg> --help-recursive`,
`<pkg> mcp list-tools`, and `ls _skills/<pkg>/` — so the README can't
drift from reality. Tracked under scitex-dev TODO.

## Four Freedoms Footer

```markdown
## Part of SciTeX

PACKAGE is part of [**SciTeX**](https://scitex.ai).

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
  <a href="https://scitex.ai" target="_blank"><img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40"/></a>
</p>

```
