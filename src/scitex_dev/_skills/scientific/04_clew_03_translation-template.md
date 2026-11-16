---
description: |
  [TOPIC] Per-project translation template for Clew adoption
  [DETAILS] Concrete project skeleton + step-by-step procedure for translating a `(project, dataset, research-questions)` tuple into a SciTeX project that produces a Clew-verifiable claims.json. Pairs with the scitexification playbook (`06_scitexification/`) — the playbook is the *what to do*, this is the *what to write*. Six steps: identify inputs, pre-flight checklist, scaffold, implement+iterate, validity gate, DONE. Includes the agent-vs-verifier directory split, the clean-DAG Makefile pattern, and the per-stage retry budget.
tags: [scitex-scientific-clew-translation-template]
---

# Per-project translation template

Apply once per `(project, dataset, research-questions)` tuple to bootstrap
a SciTeX project that produces a Clew-verifiable `claims.json`.

## Thesis

By requiring every claim to back-propagate through a Clew DAG to source
data, **Clew enforces that agents must have evidence — they cannot
hallucinate.** A claim with no provenance chain fails the validity gate.

## Args

| Slot | Meaning |
|---|---|
| `$ARGS[0]` | Pointer to the research questions (file path, JSON entry, doc) |
| `$ARGS[1]` | Pointer to the source material (code + data dir, paper supplement, archive, ...) |
| `$ARGS[2]` | Working dir (e.g. `/tmp/<project>-<id>`) |

## Step 0 — Inputs

Identify, from `$ARGS[0]` + `$ARGS[1]`:

- **Questions**: verbatim strings the answer file must use as keys.
- **Acceptance criterion** (optional): how a reviewer will judge an
  answer (exact value, tolerance interval, qualitative match), if the
  goals state one.
- **Evidence source**: where the answers can be derived from (logs,
  results dir, raw data).
- **Reference answers** (only if they exist, e.g. a replication check
  against published numbers): keep them **out of** the project that
  derives the claims — not as a path, env var, or mount. The project
  produces `claims.json`; a separate verifier compares it against the
  references afterwards. A project that has seen the expected numbers
  can no longer show it derived them.

## Step 1 — Pre-flight (SciTeX rules)

```
□ Read relevant SciTeX skills (scientific/, scitex-core/, scitex-io/, scitex-clew/).
□ Makefile must NOT set `SHELL := /bin/bash` (breaks @stx.session under make).
□ config/PATH.yaml: NO outer `PATH:` wrapper; values are f"..." literals.
□ @stx.session declares all 5 INJECTED params (CONFIG, COLORS, logger, plt, rngg).
□ Cross-stage I/O via stx.io.save(..., symlink_to=eval(CONFIG.PATH.X)).
□ For unknown extensions (e.g. .mmd) write directly with Path(...).write_text(...).
□ Vars consumed only by eval(CONFIG.PATH.X) need # noqa: F841.
□ Mermaid → SVG/PNG rendering needs `mmdc` + Puppeteer Chrome:
    npm i -g @mermaid-js/mermaid-cli
    npx puppeteer browsers install chrome
  Stage 05_render_dag.py auto-discovers chrome under ~/.cache/puppeteer/.
□ stx.io.load(".txt") returns list[str] of lines, NOT a single string.
  Iterate as-is or `"\n".join(lines)` if you need flat text.
□ Tips of the DAG (root inputs and final outputs) MUST be FILES, not scripts.
  Final stage ends at `claims.json` (saved via stx.io.save), not at the script node.
□ Agent vs Verifier: scripts in scripts/agent/ are @stx.session-decorated and
  register Clew runs. Anything that reads reference answers runs OUTSIDE this
  project (see below) so it never pollutes the DAG that derives the claims.
□ Source files with non-descriptive names (literal "output", "stdout"): COPY
  (not symlink) into a descriptive name in data/ before stage 1. Clew resolves
  symlinks to target basename, so a symlink "eval_output.txt" → real "output"
  shows up as "output" in the DAG. A real copy "eval_output.txt" shows clearly.
```

## Step 2 — Scaffold

```bash
mkdir -p $WORKDIR/{scripts,config,data/results,docs,tests/scripts}
git -C $WORKDIR init -q -b develop
# symlink inputs read-only:
ln -sfn <dataset>  $WORKDIR/data/source
# DO NOT link reference answers (if any) into this workspace.
```

### Agent-only work; verifier is third-party

**Critical**: the project contains ONLY the work that derives the claims
(`scripts/agent/`). Any comparison against reference answers is run by a
separate verifier (a different process / identity with its own access to
the references).

```
scripts/
└── agent/                       # @stx.session-decorated, registers Clew runs
    ├── 01_extract.py            # evidence → metrics.csv
    ├── 02_build_answers.py      # metrics.csv → report.json
    └── 03_register_claims.py    # report.json → claims.json   (DAG terminates here)
```

Required files: `Makefile` (single phase: `solve`), `config/{PATH,PARAMS}.yaml`,
the 3 agent scripts above, `tests/scripts/.gitkeep`.

### Makefile (clean-DAG pattern, agent-only)

```make
ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
.PHONY: solve clean-clew clean
all: solve
solve: clean-clew                                   # AGENT — Clew-tracked
	python3 $(ROOT)/scripts/agent/01_extract.py
	python3 $(ROOT)/scripts/agent/02_build_answers.py
	python3 $(ROOT)/scripts/agent/03_register_claims.py
clean-clew:
clean: clean-clew
	find $(ROOT)/scripts -type d -name "*_out" -prune -exec rm -rf {} +
	rm -rf $(ROOT)/data/results/*
```

**No reference-answer `verify` target inside this project.** A verifier
that compares against references runs separately and reads this
project's `claims.json` from outside. (Self-checks that need no
reference — `clew verify`, the validity gate below — do belong here.)

## Step 3 — Implement + iterate

For each stage 1→4: implement → `make solve` → if failing, read the
error, revert what you don't understand, consult Step 1 checklist,
retry. **Max 3 iterations per stage.**

## Step 4 — Validity gate

```
□ Every question / goal has an entry (value-grounded or null + reason)
□ The final stage registered N claims (= number of questions / goals)
□ For each value-grounded claim: clew.chain(<claim_value>) reaches an
  input file under data/source/ (the evidence, not the questions file)
```

If any check fails, fix the `source_file` argument in
`clew.add_claim(...)` or the upstream symlink, and retry (max 3).

## Step 5 — DONE

`make solve` exits 0 + all validity-gate boxes ticked +
`data/results/dag.mmd` non-empty + `data/results/report.json` matches
the expected schema.

Write a one-line summary:

```json
{
  "id": "...",
  "n_questions": N,
  "n_claims": N,
  "n_null_with_reason": K,
  "n_back_propagated": N,
  "wall_clock_s": ...,
  "iterations": ...,
  "blockers": []
}
```

## Related

- [04_clew_01_dag-as-map-and-evidence.md](04_clew_01_dag-as-map-and-evidence.md) — conceptual framing
- [06_scitexification/SKILL.md](06_scitexification/SKILL.md) — the scitexification playbook that drives this template
- [02_research-project_07_config-and-parameters.md](02_research-project_07_config-and-parameters.md) — `@stx.session` reference
