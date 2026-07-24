---
description: |
  [TOPIC] Notebook-cohort delta — execution, extraction, validity & scoring
  [DETAILS] The concrete implementation steps of the notebook translation delta: Step 3 notebook re-execution sketch (`jupyter nbconvert --execute` under `@stx.session`, R-kernel note), Step 4 answer extraction and the `answers.json` schema, Step 5 notebook-specific validity gate (answer count, source-file provenance, wall-clock cap), and Step 6 the third-party verifier's per-`eval_mode` scoring (`str_verifier` / `range_verifier` / `llm_verifier` → PASS/FAIL/INCONCLUSIVE). Split from [`04_clew_04_translation-notebook-delta.md`](04_clew_04_translation-notebook-delta.md).
tags: [scitex-scientific-clew-translation-notebook-delta]
---

# Notebook-cohort delta — execution & scoring

Steps 3–6 of the notebook translation delta, split from
[`04_clew_04_translation-notebook-delta.md`](04_clew_04_translation-notebook-delta.md)
(read it first for what/why, args, inputs, pre-flight, and scaffold).

## Step 3 — Notebook execution sketch

```python
# 01_run_notebook.py
from pathlib import Path
import scitex as stx
import zipfile, json, subprocess

@stx.session
def main(CONFIG=stx.INJECTED, logger=stx.INJECTED, plt=stx.INJECTED, COLORS=stx.INJECTED, rngg=stx.INJECTED):
    src_zip = Path(eval(CONFIG.PATH.SOURCE_ZIP))
    out_dir = Path(eval(CONFIG.PATH.SOURCE_DIR))
    if not (out_dir / ".unpacked").exists():
        with zipfile.ZipFile(src_zip) as zf: zf.extractall(out_dir)
        (out_dir / ".unpacked").touch()
    nb = next(out_dir.rglob("*Capsule*executed*.ipynb"), None) or next(out_dir.rglob("*.ipynb"))
    executed = Path(eval(CONFIG.PATH.EXECUTED_NB))
    subprocess.run(["jupyter", "nbconvert", "--to", "notebook", "--execute",
                    "--ExecutePreprocessor.timeout=600", str(nb), "--output", str(executed)],
                   check=True)
    stx.io.save({"nb": str(executed), "src_hash": stx.io.sha256(src_zip)},
                "executed_nb.json", symlink_to=eval(CONFIG.PATH.EXECUTED_NB_META))
    return 0
```

For Python+Jupyter capsules this is enough. For R-kernel capsules the
same pattern works once IRkernel is on `$PATH`.

## Step 4 — Answer extraction

For each question under this capsule, parse the executed notebook
(cells' outputs) for the relevant numeric / string / categorical answer.
Keys must match the verbatim `question` string (or use `question_id`;
pick one and stay consistent — `question_id` is shorter and stable).

`answers.json` schema:

```json
{
  "capsule_uuid": "...",
  "short_id": "bix-1",
  "n_questions": 4,
  "answers": [
    {"question_id": "bix-1-q1", "value": 0.0002, "evidence": {"cell": "...", "method": "..."}}
  ]
}
```

## Step 5 — Validity gate (notebook-specific)

```
□ len(answers) == number of rows in questions JSONL with this capsule_uuid
□ Every claim's source_file points at the executed notebook (or a downstream
  CSV/JSON that itself derives from the notebook), NOT at the masked
  questions file (which is the question schema, not the evidence).
□ Notebook execution wall-clock time recorded; if it exceeds the per-capsule
  cap (60 min default), the agent stops and reports a `timeout` blocker
  rather than emitting partial claims.
```

## Step 6 — Third-party verifier (FYI; not the agent's job)

Out of scope for the agent. Provided here only so the launcher operator
knows what the verifier project (separate yaml, separate identity,
oracle-mounted) will do:

```python
# (third-party process — runs OUTSIDE the agent's workdir)
def score_one(pred, oracle, mode):
    if mode == "str_verifier":
        return pred.strip().lower() == oracle.strip().lower()
    if mode == "range_verifier":
        try:
            p, o = float(pred), float(oracle)
            return abs(p - o) <= max(abs(o) * 0.10, 1e-12)
        except (TypeError, ValueError):
            return False
    if mode == "llm_verifier":
        return None  # INCONCLUSIVE — flag for human / LLM review out-of-band
    raise ValueError(mode)
```

The `llm_verifier` rows do not pass deterministically — the verifier
marks them INCONCLUSIVE rather than PASS/FAIL. For the cohort aggregate
metric, report PASS / FAIL / INCONCLUSIVE counts side by side.
