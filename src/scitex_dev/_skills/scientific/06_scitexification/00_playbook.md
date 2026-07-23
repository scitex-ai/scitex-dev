---
description: |
  [TOPIC] Universal scitexify playbook — the layer-agnostic translation act.
  [DETAILS] Canonical playbook for **scitexification**: the act of taking ANY scientific problem (a script, a notebook, a small repo, a paper supplement, a published analysis) and translating it into a SciTeX project — canonical structure, `@stx.session` discipline, DAG/pipeline conventions, source-grounded outputs — then re-solving it within that structure. This leaf is the GENERAL layer: it COINS the vocabulary (`scitexify` verb / `scitexification` noun) and fixes the universal contract. Experiment-specific layers (experiment-specific evaluation/scoring/output gates, etc.) live separately and compose ON TOP of this skill via `04_clew_*`. The core scientific-integrity principle — "honest source-grounding WITHOUT over-abstaining: attempt every claim, ground where possible, and when ungroundable include the claim explicitly with `null` + a reason — NEVER silently omit" — is framed here as a general scientific norm, not an output-schema rule. To actually translate-and-resolve, scitexification DEPENDS on four package-level companion skills that supply the API knowledge: scitex.session (the `@stx.session` framework), scitex.io (save/load I/O), scitex.plt + figrecipe (figures), and scitex.clew (provenance / source-grounding / validity chain). Load these alongside this playbook — see the "Required companion skills" section below for the canonical declaration and the SAC `spec.skills.required` snippet.
tags: [scitex-scientific-scitexification-playbook]
requires:
  - scitex-session
  - scitex-io
  - figrecipe
  - scitex-clew
---

# Scitexify — universal playbook

The single canonical playbook for **scitexification**, the act of converting
arbitrary scientific code into a SciTeX project. Layer-agnostic by
construction: nothing here is tied to a specific experiment's harness
(evaluation gates, scoring, output schemas). Specializations layer on top
(see [Related](#related)).

This router carries the vocabulary, the "what it is / is not" framing, and
the universal inputs. The stage-specific machinery moves into sibling
leaves — see [Chapters of this playbook](#chapters-of-this-playbook).

## Vocabulary (canonical)

- **scitexify** *(verb, transitive)* — to convert an existing scientific
  artefact (script, notebook, supplement, repo) into the SciTeX idiom.
  *Example: "scitexify the notebook before we add stats."*
- **scitexification** *(noun)* — the act, or its result. *Example: "the
  scitexification of this analysis is stage-2-complete."*
- **scitexified** *(adjective, past participle)* — describes a project that
  has been through the playbook below. *Example: "a scitexified script
  has `@stx.session`-decorated entry points."*

These three forms are the ecosystem's canonical vocabulary. Use them in PR
titles, docstrings, commit messages, and skill descriptions instead of
ad-hoc terms ("port to scitex", "scitex-ify", "convert to stx").

## Required companion skills

To actually translate-and-resolve in the SciTeX way you need the four
package-level companions (session, io, plt, clew) and the umbrella-tag
loading contract — see
[06_companion-skills.md](06_companion-skills.md).

## What scitexification *is*

Five staged transforms. Each holds independently — partial scitexification
is meaningful. Stop at any stage; the remaining work is strictly additive.

| Stage | What changes | What stays the same |
|---|---|---|
| 1. I/O patterns | Every `open()` / `np.load` / `pd.read_csv` / `pickle.load` → `stx.io.load(...)`. Every `np.save` / `pickle.dump` / `df.to_csv` → `stx.io.save(..., symlink_to=eval(CONFIG.PATH.X))`. The DAG (output of step N = input of step N+1) becomes visible at the filesystem level. | Your algorithm. Your data shapes. Your business logic. |
| 2. Session + config | The script entry-point becomes `@stx.session.start(...)`. Magic numbers + paths become `CONFIG.<KEY>` lookups against `config/*.yaml`. Logging becomes the session logger. | Function-call structure. Module organisation. Test cases. |
| 3. Figures | Every `plt.savefig(...)` → `stx.io.save(fig, ...)` so the figure is bound to a session output. Visual choices ladder up to FigRecipe's publication-quality primitives. | Figure intent (what comparison, what axis labels). What information the figure carries. |
| 4. Claims + provenance | Final-mile assertions (numbers in the abstract / conclusions) become **registered claims**, each evidence-bound to the file that produced it. Hand-written result JSON is replaced by an iterate-and-filter over registered claims. | What you are claiming. Your numbers. |
| 5. Naming + numbering | `cnn_v3_final_FIXED2.py` → `scripts/03_cnn.py` (zero-filled, sortable, mirrored under `tests/`). IDs and ordinals become readable symlinks per `02_research-project_09`. | Your filenames as a *concept*. The numbers themselves (after zero-fill). |

Stages 1+2 alone give you a *runnable* SciTeX project — the minimum viable
scitexification. Stages 3, 4, 5 are independently additive PRs.

## What scitexification *is not*

- **Not a search-and-replace.** Each stage requires you to read the
  surrounding logic. `df.to_csv("./out.csv")` → `stx.io.save(df,
  "./out.csv")` is wrong: the second arg should be the CONFIG path key
  resolved via `eval(CONFIG.PATH.X)`, not the literal.
- **Not an algorithm change.** The science stays. If the original computes
  a paired t-test on log-transformed counts, the scitexified version
  computes the same paired t-test on the same log-transformed counts.
- **Not a rewrite.** Stage 1's I/O swap is local and surgical. If the
  original calls a helper from `utils/parse_logs.py`, the scitexified
  version still calls `utils/parse_logs.py` — only the file *open* inside
  it moves to `stx.io.load`.
- **Not coupled to any specific evaluator.** Whether the project's outputs
  are later checked by a human reviewer, an LLM judge, a third-party
  verifier, or no one — scitexification is the same five stages. The
  evaluator is a separate concern.

## Universal inputs

The playbook takes exactly three slots. Anything beyond this is an
experiment-specific extension and belongs in a downstream layer.

| Slot | Meaning |
|---|---|
| `$SRC` | The thing being scitexified: a directory, a single notebook, a tarball, a git URL. **Read-only** to the agent / author. |
| `$WORKDIR` | The destination — the agent-writable directory where the scitexified project will live. |
| `$QUESTIONS_OR_GOALS` (optional) | A pointer to what the scientific output should answer or demonstrate. Free-form: a list of research questions, a notebook's conclusion section, an issue body, a paper's abstract. If absent, the goals are inferred from `$SRC`. |

The scitexification act produces a SciTeX project under `$WORKDIR` whose
DAG terminates in one or more **registered claims** plus their evidence
chain. Nothing else is required at this layer.

## Pre-flight & phase dispatch

The universal pre-flight checklist (apply BEFORE writing code) and the
four-phase stage-1 dispatch (read / notebook / repro-doc / infer) live in
[07_preflight-and-dispatch.md](07_preflight-and-dispatch.md).

## Honest source-grounding (the integrity principle)

The scientific-integrity contract — attempt every claim, ground where
possible, record ungroundable claims explicitly with `null` + a reason,
never silently omit — lives in
[08_honest-grounding.md](08_honest-grounding.md).

## Done condition, forbidden, on failure

The universal done condition, the forbidden floor, and the on-failure
(three-iterations-then-null) rule live in
[09_done-and-constraints.md](09_done-and-constraints.md).

## What this skill does NOT cover

Deliberately out of scope — the boundary list lives in
[09_done-and-constraints.md](09_done-and-constraints.md).

## Chapters of this playbook

- [06_companion-skills.md](06_companion-skills.md) — the four required
  companion skills, declarative loading, umbrella-tag contract.
- [07_preflight-and-dispatch.md](07_preflight-and-dispatch.md) —
  universal pre-flight rules + four-phase dispatch.
- [08_honest-grounding.md](08_honest-grounding.md) — the honest
  source-grounding integrity principle.
- [09_done-and-constraints.md](09_done-and-constraints.md) — done
  condition, forbidden floor, on-failure rule.

## Related

- [SKILL.md](SKILL.md) — the 5-stage arc table and "when to load" gate.
- [`../04_clew_01_dag-as-map-and-evidence.md`](../04_clew_01_dag-as-map-and-evidence.md)
  — DAG-as-map vs DAG-as-evidence framing. Read after this playbook
  when adopting clew.
- [`../04_clew_02_translation-playbook.md`](../04_clew_02_translation-playbook.md)
  — clew-specific translation playbook. Specialisation of stages 1+2+4
  for the clew-tracked flow.
- [`../04_clew_03_translation-template.md`](../04_clew_03_translation-template.md)
  — concrete project skeleton for clew-tracked translation.
- [`../02_research-project_07_config-and-parameters.md`](../02_research-project_07_config-and-parameters.md)
  — `@stx.session` reference (required by stage 2).
