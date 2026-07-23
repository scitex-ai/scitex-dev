---
description: |
  [TOPIC] README Examples — Header, Problem/Solution, Installation
  [DETAILS] Copy-paste real-README example blocks for the top of a SciTeX package README — the header (logo, tagline, quick links, badge row), the Problem and Solution table (the umbrella `scitex` five-row example), and the Installation section with the `uv pip install` lead form plus per-module extras collapsible. Use when drafting the header/install portion of a README from a worked example.
tags: [scitex-general-docs-readme]
---

# README Examples — Header, Problem/Solution, Installation

## Project README.md Examples

### Header

``` markdown
# SciTeX (<code>scitex</code>)

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/assets/images/scitex-logo-blue-cropped.png" alt="SciTeX" width="400">
  </a>
</p>

<p align="center"><b>Python Library for Science. For AI and Human Researchers</b></p>

<p align="center">
  <a href="https://badge.fury.io/py/scitex"><img src="https://badge.fury.io/py/scitex.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/scitex/"><img src="https://img.shields.io/pypi/pyversions/scitex.svg" alt="Python Versions"></a>
  <a href="https://scitex-python.readthedocs.io"><img src="https://readthedocs.org/projects/scitex-python/badge/?version=latest" alt="Documentation"></a>
  <a href="https://github.com/ywatanabe1989/scitex-python/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ywatanabe1989/scitex-python" alt="License"></a>
</p>

<p align="center">
  <a href="https://scitex-python.readthedocs.io">Docs</a> &middot;
  <a href="https://scitex-python.readthedocs.io/en/latest/quickstart.html">Quick Start</a> &middot;
  <a href="https://scitex-python.readthedocs.io/en/latest/api/index.html">API</a> &middot;
  <code>pip install scitex[all]</code>
</p>

---
```

### Problem and Solution

``` markdown
This repository provides `scitex`, the orchestration layer of the SciTeX ecosystem — solving key problems in scientific research:

## Problem and Solution

| # | Problem | Solution |
|---|---------|----------|
| 1 | **Fragmented tools** -- literature search, statistics, figures, and writing each require separate tools with incompatible formats | **Unified toolkit** -- `import scitex as stx` provides 73 modules under one namespace, accessible via Python API, CLI, and MCP. These modules are standalone packages but loosely coupled through a plugin registry — each works on its own, yet composes into designed synergy (save a figure → auto-exports CSV + YAML recipe → hash-tracked by Clew → citeable in scitex-writer). |
| 2 | **No verification** -- existing tools address whether work *could* be reproduced, not whether it *has* been verified | **Cryptographic verification** -- Clew builds SHA-256 hash-chain DAGs linking every manuscript claim back to source data |
| 3 | **AI agents lack context** -- general-purpose LLMs cannot operate across the full research lifecycle without domain-specific tools | **323 MCP tools** -- AI agents run statistics, create figures, search literature, and compile manuscripts through structured tool calls |
| 4 | **No custom tooling** -- every lab needs domain-specific tools, but building and sharing them requires deep infrastructure knowledge | **App Maker and Store** -- researchers create custom apps with [scitex-app](https://github.com/ywatanabe1989/scitex-app) SDK and share via [SciTeX Cloud](https://scitex.ai) |
| 5 | **Vendor lock-in** -- cloud research tools (Overleaf, Zotero, Mendeley, Colab, GitHub Copilot) keep data on third-party servers and depend on APIs that can disappear overnight or monetize tomorrow | **Open and self-hostable** -- every SciTeX package is AGPL-3.0; the full 39-package ecosystem runs on your own hardware (or SciTeX Cloud which itself is self-hostable); cloud integrations are pluggable extras, not requirements |
```

### Installation

Every package's README **must** lead the Installation section with
`uv pip install <package>[all]` as the recommended form. uv's parallel
Rust resolver handles the SciTeX dep set in 1-3 min where pip's serial
backtracker can take 30+ min on the full extras. Plain `pip install`
remains supported and SHOULD be shown alongside as the fallback, never
removed. See sibling rule
[02_package/10_dev-venv-isolation.md](../02_package/10_dev-venv-isolation.md)
for the per-package `.venv/` convention this works with.

The umbrella `scitex` README is canonical:

``` markdown
## Installation

```bash
# Recommended — uv resolver (10-30× faster than pip on the full extras set)
uv pip install scitex[all]

# Plain pip — slower (~30-90 min on first install; see Installation Tips)
pip install scitex[all]
```

<details>
<summary><strong>Per-module extras</strong></summary>

```bash
pip install scitex                     # Core only (minimal)
pip install scitex[plt,stats,scholar]  # Typical research setup
pip install scitex[plt]                # Publication-ready figures (figrecipe)
pip install scitex[stats]              # Statistical testing (23+ tests)
pip install scitex[scholar]            # Literature search, PDF download, BibTeX enrichment
pip install scitex[writer]             # LaTeX manuscript compilation
pip install scitex[audio]              # Text-to-speech
pip install scitex[ai]                 # LLM APIs (OpenAI, Anthropic, Google) + ML tools
pip install scitex[dataset]            # Scientific datasets (DANDI, OpenNeuro, PhysioNet)
pip install scitex[browser]            # Web automation (Playwright)
pip install scitex[capture]            # Screenshot capture and monitoring
pip install scitex[cloud]              # Cloud platform integration
```

Requires Python 3.10+. We recommend [uv](https://docs.astral.sh/uv/) for fast installs.
</details>
```
