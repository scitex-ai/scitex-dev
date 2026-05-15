---
description: |
  [TOPIC] Docs Readme Template
  [DETAILS] .
tags: [scitex-general-docs-readme-template]
---

# Canonical SciTeX README Template

Literal template for every SciTeX package README.md. Replace `<PACKAGE>`
(distribution name, e.g. `scitex-io`), `<MODULE>` (import name, e.g.
`scitex_io`), and `<TAGLINE>` (one-line value proposition) before
committing. The audit rules PS-107 / PS-109 / PS-110 / PS-111 / PS-112 / PS-133
enforce the load-bearing parts of this template.

**Reference implementations** (look at these first when in doubt):

- `~/proj/figrecipe/README.md` — original canonical layout
- `~/proj/newb/README.md` — secondary worked example with the same shape

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

```markdown
# <PACKAGE>

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-logo-blue-cropped.png" alt="SciTeX" width="400">
  </a>
</p>

<p align="center"><b><TAGLINE></b></p>

<p align="center">
  <a href="https://<PACKAGE>.readthedocs.io/">Full Documentation</a> · <code>pip install <PACKAGE></code>
</p>

<!-- scitex-badges:start -->
<p align="center">
  <a href="https://pypi.org/project/<PACKAGE>/"><img src="https://img.shields.io/pypi/v/<PACKAGE>.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/<PACKAGE>/"><img src="https://img.shields.io/pypi/pyversions/<PACKAGE>.svg" alt="Python"></a>
  <a href="https://github.com/ywatanabe1989/<PACKAGE>/actions/workflows/test.yml"><img src="https://github.com/ywatanabe1989/<PACKAGE>/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://codecov.io/gh/ywatanabe1989/<PACKAGE>"><img src="https://codecov.io/gh/ywatanabe1989/<PACKAGE>/graph/badge.svg" alt="Coverage"></a>
  <a href="https://<PACKAGE>.readthedocs.io/en/latest/"><img src="https://readthedocs.org/projects/<PACKAGE>/badge/?version=latest" alt="Docs"></a>
  <a href="https://www.gnu.org/licenses/agpl-3.0"><img src="https://img.shields.io/badge/license-AGPL_v3-blue.svg" alt="License: AGPL v3"></a>
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

> **Recommended**: `uv pip install <PACKAGE>[all]` —
> uv's Rust resolver handles the SciTeX dep set in 1-3 min where
> pip's serial backtracker can take 30+ min on the full extras.
> Plain `pip install` still works; the install block below shows both.

```bash
# Recommended — uv resolver
uv pip install <PACKAGE>[all]

# Plain pip also works
pip install <PACKAGE>
```

## Quick Start

```python
from <MODULE> import <api>
# minimal end-to-end example
```

## Part of SciTeX

`<PACKAGE>` is part of [**SciTeX**](https://scitex.ai).

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

## Audit Rules That Enforce This Template

Each rule warns (never errors) and fires from
`scitex-dev ecosystem audit-project <pkg>`.

| Code  | Enforces                                                        |
|-------|-----------------------------------------------------------------|
| PS-106 | Coverage badge present in first ~4 KB                           |
| PS-107 | Required H2 sections: `## Installation`, `## Quick Start`, `## Part of SciTeX` |
| PS-109 | PyPI version badge present in first ~4 KB                       |
| PS-110 | Four Freedoms for Research blockquote present                   |
| PS-111 | Banned personal email `ywatanabe@scitex.ai` not present         |
| PS-112 | SciTeX logo image present in first ~4 KB                        |
| PS-133 | Badges block placed below the Full-Doc line in the centered `<p align="center">` form (figrecipe-style); not above the logo and not in `[![…]]()` markdown form |

## Workflow status badges — use `?label=...` short labels

The literal template above uses the simple `test.yml/badge.svg` form.
Packages that follow PS-164 ship descriptive workflow filenames
(`pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml`), which makes the
default GitHub badge text unreadable. Switch to shields.io with an
explicit `?label=...`:

```html
<a href="https://github.com/<owner>/<PACKAGE>/actions/workflows/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml">
  <img src="https://img.shields.io/github/actions/workflow/status/<owner>/<PACKAGE>/pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml?branch=develop&label=tests"
       alt="tests">
</a>
```

The badge URL keys on the (descriptive) filename; the rendered short
label keys on shields.io. Don't rename the workflow file to match the
label — the descriptive filename is required by PS-164.

## Acceptable Variants

- Logo path: either `docs/scitex-logo-blue-cropped.png` or
  `docs/assets/images/scitex-logo-blue-cropped.png` (both occur in
  the wild). Banner variants (`scitex-logo-banner.png`) are also
  acceptable as long as the basename starts with `scitex-logo`.
- Quick Start heading: `## Quick Start` or `## Quickstart` (both
  pass PS-107).
- PyPI badge: `badge.fury.io/py/<pkg>.svg` or
  `img.shields.io/pypi/v/<pkg>.svg`.
- `import` idiom in code blocks: both `import scitex` and
  `import scitex as stx` are acceptable. Pick one and stay
  consistent within a single README.
