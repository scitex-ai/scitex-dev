---
description: |
  [TOPIC] README Standard Section Order
  [DETAILS] The canonical top-to-bottom section order for every SciTeX package README — H1, logo, tagline, quick links, badges, Problem/Solution, Quick Start, Installation, How it works / Architecture, N Interfaces, Lint Rules, Claude Code hook, Part of SciTeX, and the required first-paragraph blockquote plus optional umbrella-synergy snippet. Use when scaffolding a new README or checking section ordering.
tags: [scitex-general-docs-readme]
---

# README Standard Section Order (SciTeX)

## Standard Section Order

Every SciTeX package README follows this structure:

```markdown
# package-name

[Centered SciTeX logo]

**One-line tagline**

[Quick links: Documentation · pip install — centered]

[Badges: PyPI, Docs, Tests, License] ← placed JUST ABOVE the `---`
separator (not under the H1). The header reads top-to-bottom as
identity (logo + tagline + install link) → CI status (badges) → content.

---

## Problem and Solution                ← one combined H2; table layout
<details><summary>Supported Formats / Feature Table</summary></details>
## Quick Start                          ← top-level, tight runnable demo
## Installation                         ← one `uv pip install pkg[all]` line
## How it works (or `## Architecture`)  ← subsections explaining design;
                                          one diagram total is enough
                                          (see PS-141 / PS-142 below)
## <N> Interfaces (Python · CLI · MCP · Skills · HTTP optional)
  ← All four interface blocks MAY be collapsed `<details>` — no longer
    required to have at least one `<details open>` (PS-131 relaxed).
    NO standalone `## Modules` H2 either (PS-132; duplicates autoapi
    and drifts).
## Lint Rules (if applicable)
## Claude Code Integration as a Hook (if applicable)
## Part of SciTeX

**Required first paragraph** (one standardized line):

> `<package>` is part of [**SciTeX**](https://scitex.ai). Install via
> the umbrella with `pip install scitex[<extra>]` to use as
> `scitex.<module>` (Python) or `scitex <subcommand> ...` (CLI).

Replace `<package>`, `<extra>`, `<module>`, `<subcommand>` per package.
Do NOT use the older `> **SciTeX users**: ...` blockquote form (drifts;
inconsistent across the ecosystem).

[Optional `import scitex` snippet — ONLY include if it demonstrates
 **synergy via the umbrella**: an advantage you only get when combined
 with OTHER scitex packages through `import scitex`. Concretely, the
 snippet must touch at least TWO scitex modules and the combination must
 produce a meaningful result the standalone package cannot.

 Examples of valid synergy:
   import scitex as stx
   data = stx.io.load("session.npy")          # scitex-io
   fig, ax = stx.plt.subplots()               # scitex-plt
   ax.plot(data)
   stx.io.save(fig, "out.png")                # plt → io round-trip

 NOT synergy (skip the snippet entirely):
   import scitex
   scitex.ssh.setup(2222, ...)                # same call as scitex_ssh.setup
                                              # — different alias, no benefit

 If your package has no umbrella synergy yet, omit the snippet and ship
 only the Four Freedoms blockquote. Don't fabricate a single-module
 example just to fill the section.]
[Four Freedoms blockquote — always present]

---

[Centered SciTeX icon footer]

```
