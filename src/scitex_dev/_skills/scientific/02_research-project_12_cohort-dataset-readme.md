---
description: |
  [TOPIC] Cohort dataset README — necessary and sufficient
  [DETAILS] The required-and-sufficient structure for every `data/<cohort>/src/README.md`: the ordered required sections (Identity / Size and contents / Layout / How to (re)acquire / Padding policy / Caveats), what to leave OUT (project motivation, upstream marketing, scientific interpretation, future-work, run instructions), and the audit checklist. Split from [`02_research-project_08_cohort-datasets.md`](02_research-project_08_cohort-datasets.md).
tags: [scitex-scientific-research-project-cohort-datasets]
---

# Cohort dataset README

The README contract for a cohort dataset, split from
[`02_research-project_08_cohort-datasets.md`](02_research-project_08_cohort-datasets.md)
(which holds the directory tree, symlink, padding, scripts, and audit rules).

## Dataset README — necessary and sufficient

Every `data/<cohort>/src/README.md` (and any standalone dataset README) must be **necessary and sufficient**:

- **Necessary**: contains every fact a re-runner / reviewer needs to understand the dataset's identity, layout, and provenance.
- **Sufficient**: nothing more. No marketing prose, no aspirational paragraphs, no "we plan to also...".

### Required sections (in this order)

```markdown
# Cohort <X> — <Short name> (<Source institution>)

## Identity
- Source: <upstream URL / repo / DOI>
- Version / snapshot date: <YYYY-MM-DD or commit hash>
- Citation: <BibTeX key or one-line ref>
- License: <SPDX or upstream wording>
- Access: <public | gated (how to request) | local-only>

## Size and contents
- Items: N capsules / problems / subjects (after dedup)
- Disk: ~XX GB compressed, ~YY GB extracted
- Languages / file types: <Python N, R M, notebooks K, data-only L>
- Naming: capsule-NN -> upstream-id (zero-padded; see padding policy)

## Layout
\```
data/<cohort>/
├── capsules/         (ordinal symlinks — human-facing)
└── src/
    ├── capsules/     (raw upstream artefacts; read-only convention)
    ├── capsules_extracted/  (extractions; gitignored, regenerable)
    ├── inventory.json
    └── README.md     (this file)
\```

## How to (re)acquire
- Download:    `bash scripts/cohorts/<cohort>/dataset/download.sh`
- Extract:     `bash scripts/cohorts/<cohort>/dataset/extract.sh`
- Inventory:   `python scripts/cohorts/<cohort>/dataset/build_inventory.py`
- Inspect one: `python scripts/cohorts/<cohort>/dataset/inspect_capsule.py`

## Padding policy
<one line — width and rationale; e.g. "2 digits because max upstream ID = 49">

## Caveats
<known issues, gotchas, broken upstream items, license restrictions on derivatives, etc.>
```

### What to leave out

- ❌ The motivation for why this paper exists (that's the project README).
- ❌ Upstream's marketing copy. Link instead.
- ❌ How to interpret the data scientifically (that's per-experiment README under `scripts/cohorts/<cohort>/<experiment>/README.md`).
- ❌ Future-work bullets ("we will also add..."). Tracked in TODO/issues, not the dataset README.
- ❌ Step-by-step running of experiments. README documents the *dataset*; the Makefile documents how to run.

### Audit checklist

- [ ] All seven required sections present.
- [ ] Every command in "How to (re)acquire" actually runs as written.
- [ ] Padding policy line matches actual `capsules/<id>` widths.
- [ ] No section longer than ~5 lines unless absolutely necessary.
