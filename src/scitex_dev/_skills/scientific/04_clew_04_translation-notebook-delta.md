---
description: |
  [TOPIC] Notebook-cohort delta on top of the universal Clew translation
  [DETAILS] Per-capsule playbook for projects whose evidence source is a published Jupyter notebook (e.g. BixBench / FutureHouse). Read on top of `04_clew_03_translation-template.md` — this is a delta, not a replacement. Captures the two-stage flow (`scitex-notebook convert` → flat `.py` → standard SciTeX translation), notebook-specific pre-flight (kernel detection, determinism, cached API lookups), one-claim-per-question rule, and per-eval_mode scoring (`range_verifier`, `str_verifier`, `llm_verifier`).
tags: [scitex-scientific-clew-translation-notebook-delta]
---

# Notebook-cohort delta

Per-capsule playbook addendum for projects whose evidence source is a
published Jupyter notebook (BixBench / FutureHouse and similar). This is
a delta on the base translation template; **read
[04_clew_03_translation-template.md](04_clew_03_translation-template.md)
first**.

## What is different from non-notebook cohorts

| Aspect | Non-notebook (e.g. CORE-Bench) | Notebook (e.g. BixBench) |
|---|---|---|
| Evidence source | pre-computed `results/` dir (HTML / JSON / log) | a HuggingFace zip containing a published Jupyter notebook + raw data |
| Agent must execute code? | NO (read results only) | YES — re-execute the notebook deterministically |
| Question schema | per-capsule key/value in masked questions JSON | global `BixBench.jsonl` (or similar), indexed by `question_id` |
| Eval modes | numeric (range / equality) | `str_verifier`, `range_verifier`, `llm_verifier` mixed |
| Oracle field(s) | one numeric value per task | `ideal`, `answer`, `result`, `hypothesis` |

## Two-stage architecture

```
       capsule .zip
            │
            │ 1) unzip → data/source/
            ▼
   .../<NotebookName>.ipynb
            │
            │ 2) scitex-notebook convert --mode unified -o stage1.py
            ▼
        stage1.py            (DAG-ordered, @stx.session-decorated, untracked-IO removed)
            │
            │ 3) standard SciTeX translation (04_clew_03_translation-template.md)
            ▼
   scripts/agent/{01_run_notebook,02_extract_answers,03_register_claims}.py
   scripts/verify/{score,render_dag,make_figure}.py
   config/{PATH,PARAMS}.yaml + Makefile
            │
            │ 4) make solve / make verify
            ▼
   data/results/claims.json + dag.mmd + score.json
```

Step 2 is the only thing that's actually new. Once the notebook is a flat
Python script, the rest of the playbook is exactly the standard
SciTeX-translation flow.

## Args

| Slot | Meaning |
|---|---|
| `$ARGS[0]` | Masked questions file (in-repo, with GT fields nulled) |
| `$ARGS[1]` | Capsule .zip path (or already-extracted dir) |
| `$ARGS[2]` | `/tmp/clew-<id>` workdir |

## Step 0 — Inputs

From the masked questions file, filter by `capsule_uuid` (or convenience
id, e.g. `short_id`). Each row is one question; one capsule typically
produces 2–6 questions.

For each row capture:

```
question_id        unique id under the capsule (e.g. bix-1-q1)
question           verbatim string the agent's answer file must use as key
eval_mode          str_verifier | range_verifier | llm_verifier
distractors        present (multi-choice) — keep, NOT GT
ideal/answer/result/hypothesis  oracle-only; MASKED in the in-repo copy
```

The oracle is held by a third-party verifier and is **never exposed to
the agent** — not as a path, not as an env var, not as a container
mount. Even the location is withheld; mere knowledge of where the
oracle lives compromises masking discipline.

## Step 1 — Pre-flight (notebook-specific additions)

Add to the base checklist:

```
□ Notebook re-execution is the agent's actual work — design `scripts/agent/01_run_notebook.py`
  to (a) unzip the capsule under data/source/, (b) run the embedded notebook
  via papermill, jupyter nbconvert --execute, or (preferred) scitex-notebook's
  topological-sort compiler. Save the resulting outputs into data/results/.
□ Networked dependencies (mygene, online APIs, package indexes): cache by
  hash and pin n_jobs=1 / random seeds.
□ Kernel: notebooks are heterogeneous. Run `jupyter --kernelspec` on the
  embedded notebook before execution. R-kernel capsules need IRkernel
  installed in the container.
□ Determinism: any np/torch random seed must be set BEFORE the first cell
  that uses randomness. clusterProfiler::simplify, gseapy.enrich, mygene calls
  — all need fixed seeds + cached lookups; otherwise re-runs produce different
  hashes and the DAG breaks.
□ One claim per question, NOT one per capsule. claims.json's terminus is a
  list of length len(questions_for_this_capsule), each with claim_id =
  question_id.
```

## Step 2 — Scaffold

```
scripts/
└── agent/                       # @stx.session, in-DAG
    ├── 01_run_notebook.py       # zip → unzipped + executed notebook → outputs/
    ├── 02_extract_answers.py    # outputs/ → answers.json (one entry per question_id)
    └── 03_register_claims.py    # answers.json → claims.json (DAG terminus)
```

(No `scripts/verify/` inside the agent's project — scoring is run by a
separate third-party verifier with its own oracle access; see the base
template.)

`config/PARAMS.yaml` carries `capsule_uuid`, `short_id`,
`bixbench_jsonl_path` (or equivalent).

`data/source/` is the unzipped capsule (read-only after `unzip`).
`data/results/` holds notebook output, answers.json, claims.json,
dag.mmd, figures.

## Steps 3–6 — execution, extraction, validity & scoring

The concrete implementation steps — notebook re-execution (Step 3), answer
extraction and the `answers.json` schema (Step 4), the notebook-specific
validity gate (Step 5), and the third-party verifier's per-`eval_mode` scoring
(Step 6) — live in
[04_clew_05_notebook-execution-and-scoring.md](04_clew_05_notebook-execution-and-scoring.md).

## Why this is harder than non-notebook cohorts

Non-notebook tasks can be answered by parsing a static results file.
Notebook tasks require the agent to (1) re-execute a published Jupyter
notebook deterministically and (2) extract numeric/textual answers from
the executed output. Failure modes that don't exist in non-notebook
cohorts:

- **non-determinism**: random seeds inside the original notebook were
  not fixed; re-execution yields a different number; the DAG hash
  changes.
- **API drift**: mygene / Reactome / Ensembl lookups change over time;
  cached lookups are mandatory.
- **kernel mismatch**: notebook claims kernel `python3` but uses an R
  magic; needs IRkernel.
- **timeout**: some capsules take 30+ min just to compile the notebook
  graph; provision the per-agent cap accordingly.

These contrasts are usually the point of including a notebook cohort
alongside a non-notebook cohort in a manuscript — the comparison
exposes which failure modes the framework catches and which still
require human triage.

## Related

- [04_clew_01_dag-as-map-and-evidence.md](04_clew_01_dag-as-map-and-evidence.md) — conceptual framing
- [04_clew_02_translation-playbook.md](04_clew_02_translation-playbook.md) — universal agent prompt (selects this delta when `*.ipynb` is present)
- [04_clew_03_translation-template.md](04_clew_03_translation-template.md) — base template
- `scitex-notebook/_skills/` — `convert_notebook` API, kernel-detection, untracked-IO scan
