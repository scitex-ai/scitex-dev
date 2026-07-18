---
description: |
  [TOPIC] Ecosystem Boundary — Ports and Producers Default Convention
  [DETAILS] The decision rule for whether a new cross-package reference should be a direct import or a port/producer seam: "must the consumer work WITHOUT the producer, or should third parties plug in? -> port/producer; else -> direct import." Covers the a1/a2/b/c/d edge-kind taxonomy from the 2026-07-08 ecosystem-wide audit (67 nodes / 196 edges), the foundational-tier exemption (io/config/logging/str/dict/context/path/types), and the methodology caveat that a static import scan cannot tell a hard runtime dependency from a guarded/lazy/TYPE_CHECKING one. Read before writing any new `import scitex_<other>` / `from scitex_<other> import ...` line that crosses a package boundary.
tags: [scitex-general-ecosystem-boundary-ports-and-producers]
---

# Ecosystem Boundary — Ports and Producers

## The decision rule

Before adding a cross-package import, ask:

> **Must the consumer work WITHOUT the producer, or should third parties
> be able to plug in? → build a port/producer seam.**
> **Else → a direct import is fine.**

This is deliberately **strong but not too strong**. Wrapping a stable
foundational dependency (e.g. `scitex_io.save`) behind a port/producer
indirection is over-engineering — it buys nothing and costs a layer of
ceremony. Ports-and-producers is the default for **seams** (optional
integration points, cross-cutting signal feeds, plugin extension points),
**not** a blanket "never import a peer directly" rule.

Full rationale, the real edge-list data, and the two retracted false-alarm
case studies: `docs/adr/0003-ecosystem-boundary-ports-and-producers.md` in
scitex-dev.

## Edge-kind taxonomy

| Kind | Shape | Verdict |
| --- | --- | --- |
| **a1** — downward-to-foundational | Direct import of a **foundational-tier** package: `io`, `config`, `logging`, `str`, `dict`, `context`, `path`, `types` (8 packages). Also `scitex-dev` as a utility aggregator (39 packages import it, mostly `try_import_optional`/CLI-completion). | Always fine. Do not wrap these in a port. |
| **a2** — lateral/upward leaf→leaf | **Unguarded, top-level** import from one leaf package reaching into **another leaf package's private internals** (a `_private_module`, or an attribute/submodule past the public API/extras). | **The smell.** Fix by (a) importing the public surface instead, or (b) introducing a `_ports`/`_providers` module and moving the import there guarded/lazy (see Exemplar I below). |
| **b** — neutral-feed producer/consumer | Observer / session-hook / provenance feed where the producer has no compile-time knowledge of its consumers (e.g. `scitex_io`/`scitex_session` → `scitex_clew` observers; `scitex_todo` → `sac` card-event bus). | Fine — this is the ports pattern working. |
| **c** — entry-point plugin federation | Consumer discovers producers via `importlib.metadata` entry points, not a hard import (e.g. `scitex_dev.gate.checks`, `scitex_dev.jobs`, `scitex_dev.system_deps`; ~55 packages register `scitex_dev.docs`/`scitex_dev.skills` entry points). | Fine — this IS the ports pattern, via packaging metadata instead of an ABC. |
| **d** — optional try-import | `try: import scitex_x / except ImportError: <fallback>`, a `TYPE_CHECKING`-only import, or a lazy import inside a function body (usually paired with a `pip install <pkg>[<extra>]` error-message hint). | Fine — also the ports pattern working. |

### Worked exemplars

- **G — migration in progress**: `scitex_session → scitex_clew` is
  currently *both* a2 (legacy hard import) and b (the intended observer
  feed) at once. That is the expected shape of "a2 mid-migration to b" —
  not a steady-state violation to panic over.
- **I — a2 → d via a ports module**: `scitex_writer → scitex_scholar` was
  originally flagged a2. The fix pattern: scitex-writer introduced a
  `_ports/` (or `_providers/`) submodule holding a guarded/lazy import of
  the scholar interop; the rest of the writer package depends on the
  ports module, not on scitex-scholar directly. **Use this shape when
  converting an a2 finding into a clean d.**

## The methodology caveat (read this before writing a scanner or a lint rule)

A **static import scan alone cannot tell a hard runtime dependency from a
guarded one.** By inspection alone it cannot distinguish:

1. A genuine unguarded top-level import (the a2 smell) from
2. A `TYPE_CHECKING`-only import (zero runtime edge) from
3. A `try/except ImportError`-guarded import (kind d) from
4. A lazy import inside a function body (kind d).

Two edges in the 2026-07-08 ecosystem audit (`scitex_io → scitex_stats`,
`scitex_dev → scitex_todo`) were both flagged "priority a2" by a naive
scan and both turned out to be false alarms — cases (2) and (3)
respectively. **Any tool or reviewer classifying an import as a2 must
inspect the AST context** (is it inside a function? inside a
`try/except`? inside `if TYPE_CHECKING:`?), not just check whether the
import statement exists.

This is codified mechanically in scitex-dev's PS-183 audit rule
(`src/scitex_dev/_cli/audit/_project/_check_ecosystem_boundary.py`) —
it flags only unguarded, top-level, private-reaching, non-foundational
cross-package imports, and explicitly skips guarded/lazy/
`TYPE_CHECKING`-only imports.

## A separate overlay: packaging pins are not import edges

The umbrella (`scitex-python`)'s `==` pins on every peer package are a
**release-train determinism mechanism**, not a runtime connection. Do not
conflate a version pin in `pyproject.toml` with an import edge when
reasoning about the boundary graph.

## Quick checklist (before adding a cross-package import)

- [ ] Is the target a foundational-tier package (io/config/logging/str/
      dict/context/path/types) or `scitex-dev` as a utility aggregator?
      → direct import, done (kind a1).
- [ ] Does the consumer need to work when the producer is absent, or
      should third parties be able to plug in without the consumer
      knowing about them in advance? → build a port: entry-point
      federation (kind c) for plugin discovery, or a guarded/lazy import
      inside a `_ports`/`_providers` module (kind d) for a single
      optional integration.
- [ ] Otherwise, is this a producer emitting a neutral feed that any
      number of unknown consumers may subscribe to (kind b)? → no
      compile-time coupling needed on the producer side; the consumer
      subscribes.
- [ ] If none of the above, and the import reaches an unguarded top-level
      `from scitex_<peer> import _private_thing` or
      `scitex_<peer>._private_module` — that is the a2 smell. Either
      import the peer's public surface instead, or convert it to kind d
      via a `_ports` module (Exemplar I pattern).
- [ ] Never classify (or lint) an import as a2 without checking whether
      it is guarded, lazy, or `TYPE_CHECKING`-only first.
