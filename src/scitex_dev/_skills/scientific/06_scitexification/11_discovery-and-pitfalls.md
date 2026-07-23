---
description: |
  [TOPIC] Scitexification — tags & discovery, and the migration pitfalls.
  [DETAILS] The parent + sub-tag scheme (`scitexification` umbrella vs
  per-chapter `scitexification.io/.session/.plt/.clew/.naming`), the
  consumer-side declarative-interface target gated on the SAC discovery
  contract, the manual `tags-expand` fallback, and the five migration
  traps (hand-writing claims.json, stray plt.savefig, mixed path
  idioms, cosmetic renames, skipped tests/ mirroring). Moved verbatim
  out of SKILL.md.
tags: [scitexification, scitexification-discovery-and-pitfalls]
---

## Tags & discovery

This skill uses a parent + sub-tag scheme:

```
tags: [scitexification]              # the umbrella tag — include all 5 chapters
tags: [scitexification, scitexification.io]      # chapter 01 only
tags: [scitexification, scitexification.session] # chapter 02 only
tags: [scitexification, scitexification.plt]     # chapter 03 only
tags: [scitexification, scitexification.clew]    # chapter 04 only
tags: [scitexification, scitexification.naming]  # chapter 05 only
```

Consumer-side declarative interface (target, gated on the scitex-dev /
SAC discovery contract — see A2A thread `48d2324b`):

```yaml
# <project-root>/.scitex/dev/config.yaml
skills:
  tags: [scitexification]            # full series
  # or, for a stripped-down subset:
  tags: [scitexification.io, scitexification.session]
```

Until the declarative-discovery contract is finalized, an agent can
manually expand the tag:

```bash
scitex-dev skills tags-expand scitexification
```

and read the printed paths. The reference consumer
([proj-paper-scitex-clew](https://github.com/...)) drives the
prompt-side migration plan: their bespoke
`PROMPT_SCITEX_TRANSLATION_FOR_CLEW.md` will be retired once this
skill ships and is wired through the discovery contract.

## Pitfalls (the migration traps)

Patterns that look "almost SciTeX" but aren't, and that this skill
exists to keep you out of:

1. **Hand-writing `claims.json` / any results/output JSON** even though the
   project has Clew registered. The hand-written JSON drifts from the
   evidence-binding the registered claims actually have. Always compose
   from `scitex_clew.list_claims()` + filter on
   `scitex_clew.verify_claim(c).source_verified` — see chapter 04.
2. **Calling `plt.savefig` from a SciTeX session script** because
   "matplotlib already wrote the file." The file lands outside the
   session's output dir, gets timestamped against the wrong run, and
   silently breaks `make repro`. Always wrap in `stx.io.save(fig, ...)`
   — see chapter 03.
3. **Mixing `os.path.join(...)` and `CONFIG.PATH.<KEY>`** inside the
   same script. Either fully translate to the CONFIG lookup or stay
   fully on `os.path.join` for the call site; mixing is the loudest
   tell that scitexification stage 2 was rushed. See chapter 02.
4. **Renaming `final_v3_FIXED.py` to `script_final_v3_FIXED.py`** under
   the impression that putting it in `scripts/` is enough. Stage 5
   exists because filename hygiene is *load-bearing* for downstream
   reproducibility — see chapter 05.
5. **Skipping `tests/` mirroring** because "the script already works."
   See `../02_research-project_06_project-structure-tests.md`; the
   mirroring is what lets `audit-project` catch drift.
