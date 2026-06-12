---
description: |
  [TOPIC] Scitexification Stage 2 — Session + config
  [DETAILS] Stage 2 of the 5-stage scitexification arc: the script
  entry-point becomes `@stx.session.start(...)`; magic numbers and
  hard-coded paths become `CONFIG.<KEY>` lookups against `config/*.yaml`
  (deep-merged); ad-hoc `print` becomes the session logger. Once stage 2
  lands, every later session run gets a dated output dir, a per-run
  logger, and a single config knob to flip — which is the precondition
  for stage 3 (figure DAG hooks) and stage 4 (claim registration). Stage
  1's I/O calls keep working unchanged; they just gain a session-owned
  output root.
tags: [scitexification, scitexification-session-config]
---

<!--
Status: STUB — landed alongside SKILL.md so the umbrella's
`02_session-config.md` link in the "5-stage table" resolves to a real
file instead of a 404. Full content (the canonical `@stx.session.start`
signature, INJECTED parameter conventions, the `config/*.yaml` deep-merge
order, the `CONFIG.<KEY>` access pattern, the per-stage logger contract,
and the migration recipe for repos that already have argparse / hydra /
gin) will land in a follow-up PR scoped to this chapter only — see #119
for the five-chapter rollout plan. Cross-package details (the full
`scitex_session` public surface) live in `scitex-session`'s own
SKILL.md per the scitexification umbrella's delegation convention.
-->

# Stage 2 — Session + config

The structural step. The script's `if __name__ == "__main__": main()`
becomes `@stx.session.start(...) def main(CONFIG=stx.session.INJECTED,
...)`; magic numbers move to `config/*.yaml` and are read as
`CONFIG.<KEY>`; the bare `print` calls become `logger.info / warning /
error`. The shape of the program does not change — its entry-point and
its parameter surface do.

> **What changes**: the entry-point, the parameter-reading layer, the
> logging layer.
> **What stays the same**: function call structure, module organization,
> test cases.

## Translation table (sketch)

| Original | SciTeX equivalent |
|---|---|
| `if __name__ == "__main__": main()` | `@stx.session.start(...)` on `main` |
| `argparse` / `sys.argv` | `CONFIG.<KEY>` against `config/*.yaml` |
| `MAGIC_THRESHOLD = 0.5` (module scope) | `CONFIG.THRESHOLD` (one line in YAML) |
| `print("done")` | `logger.info("done")` (injected session logger) |
| `os.makedirs("./outputs", exist_ok=True)` | `stx.io.save(..., symlink_to=...)` under session-owned root (stage 1) |

Full inventory and the migration corner cases (existing argparse, hydra,
gin, click; partial-session shims; multi-entry-point CLIs) are pending
— see the **Status** note at the top of this file.

## Follow-up

- The full `scitex_session` public surface (the `@stx.session.start`
  signature, INJECTED parameters CONFIG / plt / COLORS / rngg / logger,
  lifecycle hooks like `on_session_start`) lives in `scitex-session`'s
  own SKILL.md.
- Stage 1 ([`01_io-patterns.md`](01_io-patterns.md)) is the precondition
  — every I/O call must already be on `stx.io.{load,save}` before the
  session-managed output dir is meaningful.
- Stage 3 ([`03_plt-patterns.md`](03_plt-patterns.md)) hooks the figure
  DAG into the session-managed output dir established here.

See also: [`00_playbook.md`](00_playbook.md) for the universal
pre-flight + done-condition; [`SKILL.md`](SKILL.md) for the 5-stage
table this chapter belongs to.
