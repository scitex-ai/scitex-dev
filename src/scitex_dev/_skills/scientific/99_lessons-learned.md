---
description: |
  [TOPIC] Lessons learned from real research projects
  [DETAILS] Concrete mistakes encountered while building paper-scitex-clew (and earlier projects), with the rule that fixed each one. Append-only — when a new failure mode is encountered, capture it here as a one-liner with a pointer to the leaf where the rule lives. Reading this leaf at project kickoff prevents the same mistake from being made twice.
tags: [scitex-scientific-lessons-learned]
---

# Lessons Learned

Append-only log of mistakes that cost real time, and the rules that fix them. Read at project kickoff.

## Hypotheses & planning

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Wrote experiment scripts before agreeing on hypotheses | Metric produced doesn't answer any user question | [`00_planning_01_hypotheses-agreement`](00_planning_01_hypotheses-agreement.md) |
| Stated "X is better" without metric/comparator | Untestable claim; reviewer rejection risk | Hypotheses must list (observable, prediction, baseline, falsification) |
| Bundled four hypotheses; user accepts two | Time wasted on H3/H4 that user never wanted | Always send back numbered, table-formatted list; let user trim |
| Assumed reader can infer "minimal logic" | Vague hypothesis; can't be tested | Either pin to a metric or drop the H |

## Project organization

The project-organization lessons table (hard-coded parameters, missing `./config/`
/ `Makefile`, the `SHELL :=` footgun, `PATH.yaml` crashes, cross-stage
`symlink_to`, README-per-directory, `.gitkeep`, cohort layout, the `GITIGNORED/`
scratch dir, …) lives in
[`99_lessons-learned_02_project-organization.md`](99_lessons-learned_02_project-organization.md).

## Naming + numbering

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| `bix-6/` next to `bix-10/` (1-digit + 2-digit) | `ls` and `for f in *` see them in wrong order | Zero-fill to max-ID width ([`./10_naming-and-numbering`](02_research-project_10_naming-and-numbering.md) rule 1) |
| Renaming UUID dirs to ordinals (lost provenance) | Can't trace back to upstream ID without a mapping table | Symlink, don't rename ([`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md) rule 1) |
| Renumbering non-contiguous upstream IDs (`bix-43, bix-45 → bix-43, bix-44`) | Manuscript citations referring to upstream `bix-44` now invalid | Preserve gaps; ordinal width is the only normalisation ([`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md) rule 3) |

## Data integrity

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Edited a CSV in `src/capsules_extracted/` to "fix" a typo | Hash drift; provenance broken; original lost | Treat extractions as ephemeral; fix in code, never on disk |
| Stored only the extracted dirs, deleted compressed originals to save disk | Can't replicate; can't compute upstream-bytes hash for provenance | Compressed `.tar.gz`/`.zip` is canonical; extractions are derived/regenerable ([`./09_id-readability`](02_research-project_09_id-readability-and-data-immutability.md) Part 2) |
| Mass-renamed files via `git mv` while `core.fileMode=false` was set | New scripts committed as 100644 (non-executable) → broken pipeline on next pull | Use `git update-index --chmod=+x`; install pre-commit hook to auto-mark `.sh`/`.src` as +x |
| Tried to "fix" the storage layer's `-32768` sentinel by rewriting the DB | Other consumers (integer-typed binary protocols, downstream DB schemas) break; sentinel was intentional | Convert sentinel → `np.nan` at the figure layer on read; treat the storage-layer sentinel as a contract, not a bug ([`figrecipe/22_nan-sentinel-on-read`](https://github.com/ywatanabe1989/figrecipe/blob/develop/src/figrecipe/_skills/figrecipe/22_nan-sentinel-on-read.md)) |

## Figures (publication-bound)

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Used `np.random.randn` to populate a "representative" figure in a paper draft | Synthetic figure traveled into slides / Slack / the PDF; reviewer caught the placeholder one revision before submission | Real-data-only policy for publication figures; fail loud (raise / non-zero exit) when real data missing; synthetic OK only in `synthetic_*` fixtures ([`./01_figures_03_no-synthetic-data-policy`](01_figures_03_no-synthetic-data-policy.md)) |
| `make_example_figure()` helper swallowed `FileNotFoundError` and rendered a stub | A "polite" placeholder figure shipped in an internal report; co-author thought it was the real result | Helper must propagate the error; refuse to write the file; never silently substitute synthetic data ([`./01_figures_03_no-synthetic-data-policy`](01_figures_03_no-synthetic-data-policy.md)) |
| Heatmap comparison with per-panel `vmin`/`vmax` "for clarity" | Visual comparison meaningless; reviewer requested redraw | Shared `vmin`/`vmax`, shared colorbar across compared panels ([`./01_figures_01_standards`](01_figures_01_standards.md), figrecipe `21_figure-prep-playbook`) |
| Hard-coded `SUBJECT_ID = 7` for the "representative example" because subject 7 looked good | Cherry-pick encoded in the pipeline; cohort change does not propagate; reviewer challenges criterion | Representative-example criterion in `CONFIG.REPRESENTATIVE.*` (median / nearest-mean / first-passing-quality), re-derived on every render; show cohort distribution alongside (figrecipe `21_figure-prep-playbook` rule 4) |
| Raw `-32768` (int16 min) values reached `vmin=data.min()` and crushed the colormap | Heatmap rendered as a single dark pixel surrounded by uniform background; "the figure is broken" — actually the sentinel leaked | Convert sentinel → `np.nan` immediately after load; use `np.nanmin`/`np.nanmax`; `cmap.set_bad("white")` for heatmaps (figrecipe `22_nan-sentinel-on-read`) |

## Tooling / dotfiles / fleet

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Stale shell session (started before dotfile fix deployed) doesn't see new env vars | "Works for me" / "doesn't work for me" inconsistencies on same host | `exec bash -l` in any pane that pre-dates the fix; or close+reopen tmux |
| Wrong `sac`/CLI version in PATH after venv activation | Subcommand "not found" even though installed | Activate the right venv before assuming `which <tool>` is correct |
| `direnv` not installed → manually `source .env` every shell | Stale env, forgotten env, project-leak across cd | Per-machine `direnv` install; `.envrc` per project |
| Per-project `.env` accidentally committed with secrets | Token leak in git history | `.env` in `.gitignore` from day one; secrets via `~/.bash.d/secrets/` |

## Communication

| Mistake | Symptom | Fix → leaf |
|---|---|---|
| Long prose answers with embedded options | User has to parse to find decision points | Numbered Q1/Q2 with a)/b) options + recommendation + tradeoffs table |
| Asking three questions in one turn | User answers one, agent loses the others | Cap at 1–2 decisions per turn ([`general/03_interface_*`](../general/03_interface/00_overview.md)) |
| Saying "untestable" when paired-arms make it testable | Wrong rejection of valid hypothesis | If a comparator + metric exist, it's testable — "vague" ≠ "untestable" |

## How to add to this list

When something costs you (or the user) > 15 min and the cause is structural (not domain-specific):

1. Add a one-row entry in the relevant section above.
2. Link to the leaf that codifies the fix; if no leaf yet, **write one** before adding the lesson.
3. Append-only: do not delete past lessons even if the failure mode is now impossible — the entry serves as a "this is why we have this rule".
