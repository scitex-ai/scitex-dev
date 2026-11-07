---
description: |
  [TOPIC] Docs Readme Template
  [DETAILS] .
tags: [scitex-general-docs-readme-template]
---

# Canonical SciTeX README Template

Literal template for every SciTeX package README.md. Replace `<PACKAGE>`
(distribution name, e.g. `scitex-io`), `<MODULE>` (import name, e.g.
`scitex_io`), `<OWNER>/<REPOSITORY>` (the actual GitHub identity),
and `<TAGLINE>` (one-line value proposition) before
committing. Substitute the checked-in workflow filenames, actual interface
commands/URLs and declared license as well. The audit rules PS-107 / PS-109 / PS-110 / PS-111 / PS-112 /
PS-133 / **PS-167 (badge layout)** enforce the load-bearing parts of
this template.

**Reference implementation (canonical)**:

- `~/proj/scitex-agent-container/README.md` — current canonical layout
  for the badge block (markers + two centered rows; see PS-167).

**Secondary reference implementations** (older worked examples):

- `~/proj/figrecipe/README.md`
- `~/proj/newb/README.md`

## Header order (load-bearing)

```
# <PACKAGE>
<centered logo>            (width=400, docs/scitex-logo-blue-cropped.png)
<centered tagline>         (<b>...</b>)
<centered Full Doc · pip>  (anchor + <code>)
<centered badges>          (figrecipe form: <p align="center"> with <a><img></a>)
[optional > blockquote]    (one-line build/auth disclaimer)
---
## Problem and Solution
```

The badges go **just below the Full-Documentation line**, NOT above.
Use the centered HTML form (`<p align="center"> ... <a href=...><img
src=...></a> ... </p>`) — NOT the left-aligned `[![…]]()` markdown
form. Inline images render as a row, centered.

## Literal template

The badge block uses the **canonical SAC layout** (PS-167):

- Order of preamble: H1 → centered logo → centered **tagline**
  (`<p align="center"><b>...</b></p>`) → centered Full-Doc + install
  line → badge block.
- Badge block is wrapped in `<!-- scitex-badges:start -->` … `<!--
  scitex-badges:end -->` markers (the markers WRAP the rows, never
  the other way around — embedding `<!-- scitex-badges:start -->`
  inside a `<p align="center">` is a PS-167 violation).
- The block contains **exactly two** `<p align="center">` rows:
  - **Row 1 — package-metadata badges**: `pypi`, `python`, `docs`.
  - **Row 2 — CI/health badges**: `tests`, `install-check`,
    `quality`, `cov`.
- Every badge image is served from `img.shields.io/...` (so it can
  carry an explicit `?label=<short>` — see PS-166's allowed
  vocabulary: `pypi`, `python`, `docs`, `tests`, `install-check`,
  `quality`, `cov`). Raw `github.com/.../badge.svg`,
  `readthedocs.org/projects/.../badge`, and `badge.fury.io` forms
  are PS-167 violations because they cannot carry a short label.

````markdown
# <PACKAGE> (<code><PACKAGE></code>)

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-logo-blue-cropped.png" alt="SciTeX" width="400">
  </a>
</p>

<p align="center"><b><TAGLINE></b></p>

<p align="center">
  <a href="https://<PACKAGE>.readthedocs.io/">Full Documentation</a> · <code>uv pip install '<PACKAGE>[all]'</code>
</p>

<!-- scitex-badges:start -->
<p align="center">
  <a href="https://pypi.org/project/<PACKAGE>/"><img src="https://img.shields.io/pypi/v/<PACKAGE>?label=pypi" alt="pypi"></a>
  <a href="https://pypi.org/project/<PACKAGE>/"><img src="https://img.shields.io/pypi/pyversions/<PACKAGE>?label=python" alt="python"></a>
  <a href="https://github.com/<OWNER>/<REPOSITORY>/actions/workflows/<DOCS_WORKFLOW>"><img src="https://img.shields.io/github/actions/workflow/status/<OWNER>/<REPOSITORY>/<DOCS_WORKFLOW>?branch=develop&label=docs" alt="docs"></a>
</p>
<p align="center">
  <a href="https://github.com/<OWNER>/<REPOSITORY>/actions/workflows/<TEST_WORKFLOW>"><img src="https://img.shields.io/github/actions/workflow/status/<OWNER>/<REPOSITORY>/<TEST_WORKFLOW>?branch=develop&label=tests" alt="tests"></a>
  <a href="https://github.com/<OWNER>/<REPOSITORY>/actions/workflows/<IMPORT_WORKFLOW>"><img src="https://img.shields.io/github/actions/workflow/status/<OWNER>/<REPOSITORY>/<IMPORT_WORKFLOW>?branch=develop&label=install-check" alt="install-check"></a>
  <a href="https://github.com/<OWNER>/<REPOSITORY>/actions/workflows/<QUALITY_WORKFLOW>"><img src="https://img.shields.io/github/actions/workflow/status/<OWNER>/<REPOSITORY>/<QUALITY_WORKFLOW>?branch=develop&label=quality" alt="quality"></a>
  <a href="https://codecov.io/gh/<OWNER>/<REPOSITORY>"><img src="https://img.shields.io/codecov/c/github/<OWNER>/<REPOSITORY>/develop?label=cov" alt="cov"></a>
</p>
<!-- scitex-badges:end -->

---

## Problem and Solution

| # | Problem | Solution |
|---|---------|----------|
| 1 | **<problem 1>** | **<solution 1>** |
| 2 | **<problem 2>** | **<solution 2>** |
| 3 | **<problem 3>** | **<solution 3>** |

## Installation

> **Recommended**: `uv pip install '<PACKAGE>[all]'` —
> Use the package's declared extras and a normal dependency resolver.
> The block below shows equivalent uv and pip installation requests; elapsed
> time depends on the selected package set and environment.

```bash
# Recommended — uv resolver
uv pip install '<PACKAGE>[all]'

# Plain pip also works
pip install '<PACKAGE>[all]'
```

## Quick Start

```python
from <MODULE> import <api>
# minimal end-to-end example
```

## Five Interfaces

| Interface | Actual package entry point |
|---|---|
| Python API | `<MODULE>` |
| CLI | `<CLI>` |
| MCP | `<MCP_COMMAND>` |
| Web API | `<WEB_API_URL>`, or explicitly unavailable |
| Skills | `<SKILL_NAMESPACE>` |

## Part of SciTeX

`<PACKAGE>` is part of [**SciTeX**](https://scitex.ai).

>Four Freedoms for Research
>
>0. The freedom to **run** your research anywhere — your machine, your terms.
>1. The freedom to **study** how every step works — from raw data to final manuscript.
>2. The freedom to **redistribute** your workflows, not just your papers.
>3. The freedom to **modify** any module and share improvements with the community.
>
>License: `<LICENSE>` — use the package's actual declared license.

---

<p align="center">
  <a href="https://scitex.ai" target="_blank"><img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40"/></a>
</p>
````

## Audit Rules That Enforce This Template

Inspect the current per-rule severity and report from
`scitex dev ecosystem audit-project <pkg>`; a convention table alone does not
establish the command's exit status or full audit acceptance.

| Code  | Enforces                                                        |
|-------|-----------------------------------------------------------------|
| PS-106 | Coverage badge present in first ~4 KB                           |
| PS-107 | Required section checks: Installation, Interfaces and Part of SciTeX; Quick Start is optional in the current implementation |
| PS-109 | PyPI version badge present in first ~4 KB                       |
| PS-110 | Four Freedoms for Research blockquote present                   |
| PS-111 | Banned personal email `ywatanabe@scitex.ai` not present         |
| PS-112 | SciTeX logo image present in first ~4 KB                        |
| PS-133 | Badges block placed below the Full-Doc line in the centered `<p align="center">` form (figrecipe-style); not above the logo and not in `[![…]]()` markdown form |
| PS-166 | Every shields.io badge uses one of the short labels `pypi`, `python`, `docs`, `tests`, `install-check`, `quality`, `cov` |
| PS-167 | Badge block uses `<!-- scitex-badges:start -->`...`:end -->` markers wrapping exactly TWO `<p align="center">` rows (metadata + CI), with every image from `img.shields.io/...` |

## Workflow status badges — use `?label=...` short labels

Use the package's actual workflow filename and branch. The literal template
uses shields.io with explicit short labels; do not invent a workflow merely to
match a copied badge URL:

```html
<a href="https://github.com/<owner>/<PACKAGE>/actions/workflows/<TEST_WORKFLOW>">
  <img src="https://img.shields.io/github/actions/workflow/status/<owner>/<PACKAGE>/<TEST_WORKFLOW>?branch=develop&label=tests"
       alt="tests">
</a>
```

The URL identifies the checked-in workflow; its short label controls the
badge text. Inspect the current PS-164 workflow rules and the leaf's existing
wrapper before choosing a filename.

## Acceptable Variants

- Logo path: either `docs/scitex-logo-blue-cropped.png` or
  `docs/assets/images/scitex-logo-blue-cropped.png` (both occur in
  the wild). Banner variants (`scitex-logo-banner.png`) are also
  acceptable as long as the basename starts with `scitex-logo`.
- Quick Start heading: `## Quick Start` or `## Quickstart` (both
  pass PS-107).
- The canonical badge block uses shields.io. A lower-level presence check
  recognizing another badge host does not mean it satisfies PS-167 layout.
- `import` idiom in code blocks: both `import scitex` and
  `import scitex as stx` are acceptable. Pick one and stay
  consistent within a single README.
