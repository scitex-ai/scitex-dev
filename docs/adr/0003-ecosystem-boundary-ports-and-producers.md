# ADR-0003: Ecosystem boundary convention — ports-and-producers as the default for seams, not a blanket no-import rule

## Status

Accepted (2026-07-10). Joint audit by scitex-writer and scitex-dev, operator-directed
(via scitex-writer, msg 307, 2026-07-08). Tracked on the scitex-todo board as
`ecosystem-dependency-diagram-ports-producers-convention-20260708`.

## Context

The SciTeX ecosystem is ~70 packages deep. As the graph grew, cross-package
imports accumulated organically with no explicit rule for when a package
should hard-import a peer versus expose/consume an extension point. The
operator asked for two things: (1) an authoritative dependency/connection
diagram (writer renders it), and (2) a decision on whether "ports and
producers" (dependency-inversion via an extension point, rather than a
direct import) should be the *default* architecture for the whole
ecosystem.

### The graph (ground truth)

scitex-dev generated a real edge-list from source — no guessing — by
scanning `.py` imports across `~/proj`, `pyproject.toml` entry-points, and
the umbrella's `==` pins:

- **67 nodes, 196 edges** — `~/.scitex/dev/runtime/ecosystem-edge-list.json`.
- Initial pass flagged **54 candidate leaf→leaf "smells"** (a2, see
  taxonomy below).
- After **context-aware re-verification** (see Methodology caveat), the two
  edges flagged as *priority* (`scitex_io → scitex_stats`,
  `scitex_dev → scitex_todo`) were **both false alarms**:
  - `scitex_io → scitex_stats`: the import lives inside `if
    TYPE_CHECKING:` in `_saver.py` — a type-only annotation, not a runtime
    edge. The real runtime path is `try_import_optional` in
    `_optional_providers.py`. Reclassified **d** (optional try-import).
  - `scitex_dev → scitex_todo`: the import is inside a `try/except`
    (fail-open soft dependency). Reclassified **d**. Minor follow-up: it
    reaches `scitex_todo`'s private `_paths`/`_store` — prefer the public
    API, but not a priority fix.
  - **Net result: zero confirmed a2 "priority" violations** in the initial
    graph. The 54 a2 candidates are *places to look*, not a list of
    confirmed bugs — a static import scan cannot, by itself, tell a hard
    runtime dependency from a guarded/lazy/type-only one.

### Framing agreed with the operator

> "Must the consumer work WITHOUT the producer, or should third parties
> plug in? → port/producer. Else → direct import is fine."

This is deliberately **strong but not too strong** — the operator's exact
worry was over-engineering: wrapping a stable foundational import (e.g.
`scitex_io.save`) behind a port/producer indirection buys nothing and
costs a layer of ceremony (YAGNI). Ports-and-producers is the default for
**seams** — cross-package signal, extension, or optional-integration
points — not a blanket "no direct import" rule.

## Decision

**Adopt the decision rule above as the ecosystem-wide default**, codified
via the edge-kind taxonomy below. The taxonomy is what the audit actually
found in the real graph, not a hypothetical model.

### Edge-kind taxonomy

| Kind | Name | Shape | Verdict |
| --- | --- | --- | --- |
| **a1** | Downward-to-foundational | Any package directly imports a **foundational-tier** package (`io`, `config`, `logging`, `str`, `dict`, `context`, `path`, `types` — 8 packages). | **Always fine.** These are infrastructure; wrapping them in a port buys nothing. Also covers the aggregator case: 39 packages import `scitex-dev` (mostly `try_import_optional` / CLI-completion utility) — kept **a1**, not a smell, because the aggregator role is a foundational-tier-like utility relationship, not a feature dependency. |
| **a2** | Lateral/upward leaf→leaf, **the smell** | An **unguarded, top-level** import from one leaf package reaching into **another leaf package's private internals** (a `_private_module`, or an attribute/submodule past the declared public API/extras). | **THE smell.** Usually wants a port/producer seam, or at minimum should import the public surface instead of the private one. Render amber in the diagram — "review candidate," not an automatic verdict (see Methodology caveat). |
| **b** | Neutral-feed producer/consumer | Observer / session-hook / provenance feed — the producer doesn't know or care who consumes (e.g. `scitex_io`/`scitex_session` → `scitex_clew` observers; `scitex_todo` → `sac` card-event bus). | **Fine — this is the ports pattern working.** The consumer subscribes; the producer has no compile-time knowledge of consumers. |
| **c** | Entry-point plugin federation | Consumer discovers producers via `importlib.metadata` entry points, not a hard import (e.g. `scitex_dev.gate.checks`, `scitex_dev.jobs`, `scitex_dev.system_deps`; near-universally, ~55 packages register `scitex_dev.docs` + `scitex_dev.skills` entry points). | **Fine — this IS the ports pattern**, formalized via setuptools/hatchling entry points instead of a Python-level abstract base. |
| **d** | Optional try-import ("connect if present") | `try: import scitex_x ... except ImportError: <fallback>`, a `TYPE_CHECKING`-only import, or a lazy import inside a function body whose docstring/error message names the extra to install. | **Fine — also the ports pattern working.** The consumer degrades gracefully when the producer is absent. Both re-verified "priority" a2 candidates above turned out to be kind **d**. |

Two edge kinds emerged as **worked exemplars** during the audit and are
worth naming explicitly for future reviewers:

- **Exemplar G — migration in progress.** `scitex_session → scitex_clew`
  is currently **both** a2 (legacy hard import) **and** b (the intended
  observer feed) simultaneously — i.e., the codebase is mid-migration from
  a hard dependency to the neutral-feed pattern. This is the canonical
  shape of "a2 in transition to b," not a steady-state violation.
- **Exemplar I — a2 reclassified as d via a ports module.** `scitex_writer
  → scitex_scholar` was originally flagged a2 (leaf→leaf). It was
  reclassified **d** because scitex-writer defines a `_ports/` module (its
  own optional-integration seam) that the scholar interop passes through,
  with a guarded optional import. This is the reference pattern for "how
  to turn an a2 into a clean d": introduce a `_ports` (or `_providers`)
  submodule, put the guarded/lazy import there, and have the rest of the
  package depend on the port module instead of the peer directly.

### A separate overlay: packaging edges

The umbrella's `==` pins (`scitex-python`'s `pyproject.toml` pinning every
peer at an exact version for release-train determinism) are a **distinct
overlay**, not a runtime connection. They get their own legend entry in
any rendered diagram and must never be mixed into the a1/a2/b/c/d
classification — a version pin is not an import.

### Methodology caveat (load-bearing — read before writing a scanner)

A **static import scan alone cannot tell a hard runtime dependency from a
guarded one.** Concretely, it cannot by inspection alone distinguish:

1. A genuine unguarded top-level import (the a2 smell), from
2. A `TYPE_CHECKING`-only import (zero runtime edge — pure type hint), from
3. A `try/except ImportError`-guarded import (kind d — ports pattern), from
4. A lazy import inside a function body (kind d — ports pattern; often
   paired with an install-hint error message).

The scanner (and the audit rule it drives, PS-183 — see the boundary-lint
PR) **must classify the AST context of each import**, not just its
presence. Cases (2)-(4) are not smells; only (1) is. This is the
concrete lesson from the two false "priority" alarms retracted in this
audit — the diagram from a naive scan is a "where to look" map, not a
verdict, and the audit tooling built on top of it must encode the same
distinction or it will reproduce the same false positives at scale.

## Consequences

**Positive**

- The ecosystem now has one documented decision rule for "should this be
  a direct import or a port/producer seam," replacing ad hoc per-PR
  judgment calls.
- The taxonomy names patterns (b, c, d) that were already in wide use
  (clew observers, `scitex_dev.gate`/`jobs`/`system_deps` entry points,
  `try_import_optional`) but had never been written down — this ADR
  documents existing practice, not a new burden.
- The a2 "smell" definition is narrow and mechanical enough to lint
  (PS-183): unguarded + top-level + reaches a peer's private surface. This
  keeps false positives low relative to a blanket "any cross-package
  import is suspect" rule.
- Two exemplars (G, I) give future contributors a concrete "how to fix an
  a2" recipe: introduce a `_ports`/`_providers` module and move the
  guarded/lazy import there.

**Negative / cost**

- 54 a2 candidates remain in the graph as review candidates. Fixing them
  is *not* mandated by this ADR — it is future, package-by-package
  cleanup work, tracked separately from this convention decision.
- The `scitex-dev ecosystem graph` CLI verb (regenerate the edge-list JSON
  + render, `--focus`/`--smells-only`) and the writer-side PNG renderer
  are **out of scope for this ADR's implementing PR** — they are
  follow-up deliverables tracked on the same scitex-todo card. This ADR
  and its accompanying skill doc + PS-183 lint rule are the "convention +
  automated a2 gate" half of that card; the visualization CLI is separate.

**Avoided cost (vs. status quo)**

- Without this ADR, every new cross-package import decision is re-litigated
  from scratch, and a naive "count all cross-package imports" audit would
  keep false-flagging kind b/c/d edges as if they were kind a2 — exactly
  the mistake this audit caught and corrected before it shipped as policy.

## Notes

- Provenance: scitex-todo card
  `ecosystem-dependency-diagram-ports-producers-convention-20260708`
  (created 2026-07-08 by proj-scitex-dev, now scitex-dev after an
  identity-routing repair). Real edge-list data:
  `~/.scitex/dev/runtime/ecosystem-edge-list.json` (67 nodes, 196 edges,
  generated 2026-07-08).
- Related ADRs: none in scitex-dev/docs/adr yet cover ecosystem boundary
  policy; ADR-0001/0002 cover a single-package absorption decision
  (different concern — this ADR is the general cross-package import rule).
- Skill reference: `_skills/general/01_ecosystem/16_boundary-ports-and-producers.md`
  — the agent-facing summary of this decision rule, to be read before
  writing any new cross-package import.
- Implementing PR: adds the PS-183 audit rule
  (`src/scitex_dev/_cli/audit/_project/_check_ecosystem_boundary.py`) that
  encodes the a2 definition mechanically (unguarded + top-level +
  private-reaching + non-foundational peer), skipping guarded/lazy/
  TYPE_CHECKING imports per the methodology caveat above.
- Open follow-ups (tracked on the same scitex-todo card, not this PR):
  1. `scitex-dev ecosystem graph` CLI verb (edge-list regeneration +
     matplotlib render, optional `[graph]` extra) — writer PRs the render
     module, scitex-dev owns the CLI/packaging/wiring.
  2. Package-by-package triage of the remaining a2 review candidates
     (54 at audit time, 2 already retracted as false alarms).
  3. Migrate `scitex_session → scitex_clew` fully from a2 to b (exemplar
     G is mid-migration, not yet steady-state).
