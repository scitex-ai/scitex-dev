---
description: |
  [TOPIC] Scitexification — required companion skills.
  [DETAILS] The four package-level companion skills scitexification
  DEPENDS on (scitex.session, scitex.io, scitex.plt + figrecipe,
  scitex.clew), what each provides per stage, declarative `requires:`
  loading, the umbrella-tag vs filename contract, and stand-alone
  reading. Moved verbatim out of 00_playbook.md.
tags: [scitexification, scitexification-companion-skills]
---

## Required companion skills

Scitexification is the *translation act*. To actually translate-and-resolve
in the SciTeX way, an agent (or human author) needs the **API knowledge**
that lives in the per-package skills. This playbook deliberately stays
package-agnostic at the surface level and DELEGATES the API surface to its
four canonical companions:

| Companion skill | What it provides for scitexification |
|---|---|
| **scitex.session** | The `@stx.session.start(...)` decorator, the CONFIG injection contract (`CONFIG`, `COLORS`, `logger`, `plt`, `rngg`), `SDIR_OUT` / `SDIR_RUN` semantics, YAML deep-merge + CLI/env overrides. **Required for stage 2** (session + config). |
| **scitex.io** | `stx.io.save(...)` / `stx.io.load(...)` with the per-extension saver/loader registry, the `symlink_to=eval(CONFIG.PATH.X)` cross-stage I/O pattern, post-save / post-load hook registration. **Required for stage 1** (I/O patterns) and **stage 4** (claims save/load). |
| **scitex.plt + figrecipe** | `stx.plt` figure objects, FigRecipe publication-quality primitives, the `stx.io.save(fig, ...)` DAG-binding for figures. **Required for stage 3** (figures). |
| **scitex.clew** | Claim registration, evidence-binding (the DAG that anchors a claim to a source file), `list_claims()` / `verify_claim()` / `render_dag()` primitives, validity-chain semantics. **Required for stage 4** (claims + provenance) and load-bearing for the honest-grounding principle below. |

The four are not interchangeable; each carries a specific role in the
five-stage arc.

### Declarative loading

This playbook's frontmatter lists the four as `requires:`. A SAC agent yaml
that loads scitexification pulls them automatically:

```yaml
spec:
  skills:
    required:
      - scitexification           # this playbook (umbrella tag)
      # The four companions below are inherited via `requires:` above.
      # List them explicitly anyway for SAC versions that don't yet
      # resolve transitive requirements:
      - scitex-session
      - scitex-io
      - figrecipe
      - scitex-clew
```

If your SAC version resolves transitive `requires:`, only the first line
is needed. If not, list all five — the duplication is harmless. The
canonical short-form everyone should learn is: **"to scitexify you need
session, io, plt, and clew."**

#### Tag vs filename: how loading the umbrella surfaces this playbook

`SKILL.md` carries the umbrella tag `[scitexification]`. This playbook
file carries the narrower tag
`[scitex-scientific-scitexification-playbook]`. The two are NOT meant
to be loaded by separate `spec.skills.required` entries — that would
double-count the same content. The contract is:

- A SAC agent loads the **umbrella** tag (`scitexification`) via
  `spec.skills.required`.
- The skills export tool mounts `~/.claude/skills/scitex/scitexification/`
  with **every sibling `.md` under the `06_scitexification/` directory
  in scitex-dev's `_skills/scientific/`** — including this `00_playbook.md`,
  the (future) `01_io-patterns.md` … `05_naming-and-numbering.md`
  chapters, and the umbrella `SKILL.md` itself.
- An agent that loads `scitexification` therefore gets both the SKILL.md
  overview AND this playbook in its skills context, without needing to
  list the narrower tag separately.

The narrower tag exists so a downstream skill that needs to reference
*only this playbook* (e.g. an internal cross-reference, a `requires:`
fold in a future per-chapter skill) can do so without pulling the whole
umbrella. For the SAC agent yaml, **always use the umbrella tag**.

### Stand-alone reading

A human reading this playbook without an agent runtime should open the
four companion `SKILL.md` files alongside this one:

```
~/.claude/skills/scitex/scitex-session/SKILL.md
~/.claude/skills/scitex/scitex-io/SKILL.md
~/.claude/skills/scitex/figrecipe/SKILL.md
~/.claude/skills/scitex/scitex-clew/SKILL.md
```

The playbook tells you *which* primitive to reach for at each stage; the
companion skill tells you *what* the primitive does. Read both.
