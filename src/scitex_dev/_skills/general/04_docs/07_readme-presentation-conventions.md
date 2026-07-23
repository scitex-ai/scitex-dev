---
description: |
  [TOPIC] README Presentation Conventions
  [DETAILS] The 2026-05 presentation conventions for SciTeX READMEs — top-level Quick Start, one-liner Installation, numbered How-it-works subsections, blockquote callouts, one-sentence Problem/Solution cells, the canonical SAC badge-row layout (PS-167) with shields.io explicit-label convention, the optional Claude Code hook section, and required interface star ratings. Use when styling or auditing a README's presentation.
tags: [scitex-general-docs-readme]
---

# README Presentation Conventions (SciTeX)

## Presentation conventions (adopted 2026-05)

### Quick Start (top-level H2)

A `## Quick Start` H2 sits between **Problem and Solution** and
**Installation**. It contains one tight runnable code block (≈10–25
lines) demonstrating the package's primary value, with a round-trip
assertion if applicable. This replaces the old role of the primary
`<details open>` interface block. With Quick Start present, every
interface inside `## <N> Interfaces` can be collapsed (PS-131 relaxed).

### Installation (one-liner)

```markdown
## Installation

```bash
uv pip install "<pkg>[all]"
```
```

No prose. The per-module extras matrix goes inside a `<details>`
collapsible directly below. Drop redundant explanations of why `uv` is
faster than `pip`; users either know or follow the link.

### How it works (numbered subsections)

`## How it works` (or the older `## Architecture` — both are accepted
by the auditor, PS-142) breaks into `### 1.`, `### 2.`, `### 3.`
subsections, each focused on one design choice. Use one mermaid
diagram between Demo and Architecture/How-it-works — the "one diagram
is enough" rule (PS-141 visual-anywhere). Mermaid init config keeps
the diagram compact:

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 20, 'rankSpacing': 40, 'curve': 'linear'}, 'themeVariables': {'fontSize': '12px'}}}%%
```

### Blockquote (`>`) callouts for high-signal asides

Use `>` to set apart rules, edge cases, opt-in extras, and "watch out"
notes. Every continuation line must carry the `>` prefix so markdown
renders one connected callout (not a broken-multi-line quote):

```markdown
> **Absolute paths bypass routing.** `sio.save(df, "/data/x.csv")`
> writes to `/data/x.csv` as-is — caller-anchored routing (§2) only
> applies when the path is relative.
```

### Problem and Solution: one sentence per cell

The `## Problem and Solution` table cells must each be a single
sentence (≤ 200 chars per cell, PS-144). Drop trailing examples and
"impossible to track" amplifications — the table is a scannable
summary, not an essay.

| # | Problem | Solution |
|---|---|---|
| 1 | **Format zoo** — every format has its own API. | **One call** dispatches across 30+ formats. |

<!-- hook-bypass: line-limit (file pre-existing over MD cap; see GITIGNORED/REFACTORING.md) -->

### Badge row — canonical SAC layout (PS-167)

Mirrors `scitex-agent-container/README.md`. Header order: H1 (with
`<code>pkg-name</code>`) → centered logo → centered **tagline**
(`<p align="center"><b>...</b></p>`) → centered Full-Doc + install
line → badge block. PS-167 enforces four rules on the badge block:

1. Wrapped in `<!-- scitex-badges:start -->` … `<!-- scitex-badges:end -->`
   markers (markers OUTSIDE the `<p>` tags — never nested inside).
2. Exactly **two** `<p align="center">` rows: row 1 = metadata
   (`pypi`, `python`, `docs`); row 2 = CI/health (`tests`,
   `install-check`, `quality`, `cov`).
3. Every image served from `img.shields.io/...` (raw
   `actions/.../badge.svg`, `readthedocs.org/.../badge`,
   `badge.fury.io` are rejected — shields.io is required so each
   badge can carry `?label=<short>`).
4. Short labels from PS-166's vocabulary; metadata row uses at least
   one of `pypi`/`python`/`docs`, CI row uses at least one of
   `tests`/`install-check`/`quality`/`cov`.

```html
<!-- scitex-badges:start -->
<p align="center">
<a href="https://pypi.org/project/<pkg>/"><img src="https://img.shields.io/pypi/v/<pkg>?label=pypi" alt="pypi"></a>
<a href="https://pypi.org/project/<pkg>/"><img src="https://img.shields.io/pypi/pyversions/<pkg>?label=python" alt="python"></a>
<a href="https://github.com/<owner>/<pkg>/actions/workflows/rtd-sphinx-build-on-ubuntu-latest.yml"><img src="https://img.shields.io/github/actions/workflow/status/<owner>/<pkg>/rtd-sphinx-build-on-ubuntu-latest.yml?branch=develop&label=docs" alt="docs"></a>
</p>
<p align="center">
<a href="https://github.com/<owner>/<pkg>/actions/workflows/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml"><img src="https://img.shields.io/github/actions/workflow/status/<owner>/<pkg>/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml?branch=develop&label=tests" alt="tests"></a>
<a href="https://github.com/<owner>/<pkg>/actions/workflows/import-smoke-on-ubuntu-py3-12.yml"><img src="https://img.shields.io/github/actions/workflow/status/<owner>/<pkg>/import-smoke-on-ubuntu-py3-12.yml?branch=develop&label=install-check" alt="install-check"></a>
<a href="https://github.com/<owner>/<pkg>/actions/workflows/scitex-dev-quality-audit-on-ubuntu-latest.yml"><img src="https://img.shields.io/github/actions/workflow/status/<owner>/<pkg>/scitex-dev-quality-audit-on-ubuntu-latest.yml?branch=develop&label=quality" alt="quality"></a>
<a href="https://codecov.io/gh/<owner>/<pkg>"><img src="https://img.shields.io/codecov/c/github/<owner>/<pkg>/develop?label=cov" alt="cov"></a>
</p>
<!-- scitex-badges:end -->
```

Drop the AGPL license badge — already in `pyproject.toml` metadata
and visible on PyPI.

#### Badge label convention: shields.io with explicit `?label=...`

Workflow filenames are deliberately descriptive
(`pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml`), which makes the
default GitHub Actions badge text unreadable. Use **shields.io's
`github/actions/workflow/status` endpoint with an explicit `?label=`
short label**. The badge URL keys on the filename (long, descriptive);
the short label keys on shields.io (so the rendered badge stays
scannable). Example:

```html
<a href="https://github.com/<owner>/<repo>/actions/workflows/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml">
  <img src="https://img.shields.io/github/actions/workflow/status/<owner>/<repo>/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml?branch=develop&label=tests"
       alt="tests">
</a>
```

Apply the same pattern to every workflow badge (`label=install`,
`label=docs`, `label=audit`, …). Do NOT rename the workflow file to
match the short label — the descriptive filename is required by PS-164
for the GitHub Actions UI; the README badge label is purely cosmetic.

### Claude Code Integration as a Hook (optional)

If the package ships lint rules, add a `## Claude Code Integration as
a Hook` section after `## Lint Rules`. Ship the hook script at
`examples/<pkg>_lint.sh` (self-contained — no dependency on the
maintainer's dotfiles). Include `settings.json` snippet that wires it
to `PostToolUse` with matcher `Edit|Write|MultiEdit`. See
[scitex-io's hook](https://github.com/ywatanabe1989/scitex-io/blob/develop/examples/scitex_io_lint.sh)
for the template.

### Interface ratings (`⭐`)

Star ratings are **required** on every interface summary (drop only
the trailing parenthetical tags like `— for AI Agents` /
`— for AI Agent Discovery`, PS-118). Use 1–3 stars per interface
reflecting its primacy:

```markdown
<details>
<summary><strong>Python API ⭐⭐⭐</strong></summary>
```

The deprecated `> **Interfaces:** ...` callout at the top of SKILL.md
files is forbidden (PS-116) — stars belong on summaries only.
