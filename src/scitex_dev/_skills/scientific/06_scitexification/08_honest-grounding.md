---
description: |
  [TOPIC] Scitexification — honest source-grounding (the integrity principle).
  [DETAILS] The scientific-integrity contract scitexification enforces:
  attempt every claim, ground where possible, and when ungroundable
  record it explicitly with `null` + a reason — NEVER silently omit.
  Covers why over-abstention / silent-attrition is forbidden, the
  WRONG/RIGHT code, schema-agnostic note, filtering-is-downstream
  separation of concerns, and why it is a general norm not a schema
  rule. Moved verbatim out of 00_playbook.md.
tags: [scitexification, scitexification-honest-grounding]
---

## Honest source-grounding (the integrity principle)

**This is the scientific-integrity contract scitexification enforces.** It
is independent of any evaluator and applies even when no one is checking.

### The principle

> Every claim a scitexified project makes about the world MUST be
> attempted, grounded against verifiable source where possible, and —
> when grounding is impossible — recorded explicitly with `null` and a
> reason. Silent omission of an ungroundable claim is forbidden.

### Why the principle is necessary

A natural failure mode under uncertainty is **over-abstention**: an agent
or author who cannot ground a claim quietly drops it. Across many runs
this becomes a **silent-attrition** pattern — the agent answers only the
easy questions, never tries the hard ones, and the output set is a
*smaller, biased subset* of the question set. The downstream record
looks clean but lies by omission, and a reviewer reading the output
**cannot distinguish three radically different states**:

1. "we tried, evidence was clear, the answer is X"
2. "we tried, the evidence was ambiguous / inaccessible"
3. "we never attempted this question"

All three collapse to the same shape: *nothing in the output*. The bias
is invisible to anyone downstream.

Scitexified projects refuse the silent failure by construction. A claim
either:

1. **Lands with `answer != null` and an evidence chain.** The evidence
   chain (Clew DAG, `stx.io` save path, registered claim) lets a
   reviewer verify the number ladders back to a file in `data/`. This
   is the desired state.

2. **Lands with `answer = null` and `reason != null`.** The reason
   explains why grounding failed — *the data was not in the supplement*,
   *the cell errored on a missing dependency*, *the published table is
   ambiguous between two reportings* — in enough detail that a human
   reviewer can decide whether to escalate, defer, or accept.

The two states are **not equivalent to success and failure**. Both are
honest outputs. The only dishonest output is the *missing* claim: a
question the project should have addressed, with no entry in the
results.

### Concretely

```python
# WRONG — silent over-abstention.
# If the value can't be extracted, drop the entry.
try:
    val = extract_accuracy(results_path)
    claims.append({"id": qid, "answer": val})
except Exception:
    pass  # ← this is the forbidden silence.

# RIGHT — explicit null with reason.
try:
    val = extract_accuracy(results_path)
    claims.append({"id": qid, "answer": val, "source": str(results_path)})
except Exception as exc:
    claims.append({"id": qid, "answer": None, "reason": str(exc)})
```

The general rule:

- **Attempt every claim.** Do not pre-emptively skip "hard" questions.
- **Ground what you can.** When the value comes from a file, record the
  file path on the claim itself (`source` / `evidence` field).
- **Be explicit about what you can't ground.** Include the claim with
  `answer: null` plus a one-sentence `reason`. The reason must be
  actionable for the next reviewer — "the source notebook errored on
  `ModuleNotFoundError: ot`" is good; "could not compute" is not.
- **Never silently omit.** A correct result is one where the *count* of
  claim entries equals the *count* of expected goals — independent of
  how many entries are `null`.

Schema note (layer-agnostic): the WRONG/RIGHT example above uses
`{answer, source}` for grounded claims and `{answer, reason}` for null
claims — two key sets. The playbook stays agnostic to the final shape;
downstream evaluators typically prefer one of two uniform schemas:
(a) **always carry both keys** with the unused one set to `null`
(`{answer, source, reason}` everywhere — easiest to parse uniformly);
or (b) **a single `evidence` field** that is either a file path string
or a reason string, with the discriminator being how it parses. Pick
whichever the consuming evaluator wants; the integrity contract is
about the *presence* of the entry, not the key set.

### Separation of concerns: filtering is downstream

If a downstream evaluator does need to filter the agent's output (a
SHA-256 lineage gate, a source-verified flag, an evidence-completeness
threshold), the filter applies **after** the agent emits — on the
verifier side, never as an instruction to the agent. Telling the agent
"if you can't ground it, omit it" produces silent attrition and
destroys the epistemic signal the verifier needs.

The agent's job is to emit a faithful record of *what it attempted and
what it found*. The verifier's job is to decide *which entries count*.
Mixing the two is the bug.

### Why this is a general principle, not an output-schema rule

This principle is older than scitex-clew and outlives any one evaluator.
It is the standard scientific-record norm: report what you found,
including what you couldn't find. Pre-registration and Methods-section
discipline operationalise the same idea. Scitexification just enforces
it in the output schema so the project's filesystem reflects the norm
mechanically.
