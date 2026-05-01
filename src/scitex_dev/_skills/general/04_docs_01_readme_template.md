# Canonical SciTeX README Template

Literal template for every SciTeX package README.md. Replace `<PACKAGE>`
(distribution name, e.g. `scitex-io`), `<MODULE>` (import name, e.g.
`scitex_io`), and `<TAGLINE>` (one-line value proposition) before
committing. The audit rules PS107 / PS109 / PS110 / PS111 / PS112
enforce the load-bearing parts of this template.

```markdown
# <PACKAGE>

<!-- scitex-badges:start -->
[![PyPI](https://img.shields.io/pypi/v/<PACKAGE>.svg)](https://pypi.org/project/<PACKAGE>/)
[![Python](https://img.shields.io/pypi/pyversions/<PACKAGE>.svg)](https://pypi.org/project/<PACKAGE>/)
[![Tests](https://github.com/ywatanabe1989/<PACKAGE>/actions/workflows/test.yml/badge.svg)](https://github.com/ywatanabe1989/<PACKAGE>/actions/workflows/test.yml)
[![Coverage](https://codecov.io/gh/ywatanabe1989/<PACKAGE>/graph/badge.svg)](https://codecov.io/gh/ywatanabe1989/<PACKAGE>)
[![Docs](https://readthedocs.org/projects/<PACKAGE>/badge/?version=latest)](https://<PACKAGE>.readthedocs.io/en/latest/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
<!-- scitex-badges:end -->

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-logo-blue-cropped.png" alt="SciTeX" width="400">
  </a>
</p>

<p align="center"><b><TAGLINE></b></p>

<p align="center">
  <a href="https://<PACKAGE>.readthedocs.io/">Full Documentation</a> · <code>pip install <PACKAGE></code>
</p>

---

## Problem and Solution

| # | Problem | Solution |
|---|---------|----------|
| 1 | **<problem 1>** | **<solution 1>** |
| 2 | **<problem 2>** | **<solution 2>** |
| 3 | **<problem 3>** | **<solution 3>** |

## Installation

```bash
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
| PS106 | Coverage badge present in first ~4 KB                           |
| PS107 | Required H2 sections: `## Installation`, `## Quick Start`, `## Part of SciTeX` |
| PS109 | PyPI version badge present in first ~4 KB                       |
| PS110 | Four Freedoms for Research blockquote present                   |
| PS111 | Banned personal email `ywatanabe@scitex.ai` not present         |
| PS112 | SciTeX logo image present in first ~4 KB                        |

## Acceptable Variants

- Logo path: either `docs/scitex-logo-blue-cropped.png` or
  `docs/assets/images/scitex-logo-blue-cropped.png` (both occur in
  the wild). Banner variants (`scitex-logo-banner.png`) are also
  acceptable as long as the basename starts with `scitex-logo`.
- Quick Start heading: `## Quick Start` or `## Quickstart` (both
  pass PS107).
- PyPI badge: `badge.fury.io/py/<pkg>.svg` or
  `img.shields.io/pypi/v/<pkg>.svg`.
- `import` idiom in code blocks: both `import scitex` and
  `import scitex as stx` are acceptable. Pick one and stay
  consistent within a single README.
