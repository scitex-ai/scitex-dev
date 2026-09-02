---
description: |
  [TOPIC] Ecosystem Version Pinning Rules
  [DETAILS] The version-pinning half of dependency hygiene — pin the minimum version that contains a feature you rely on, never an upper bound unless a release is proven broken; always set a lower bound; when you release a feature consumers need, bump their minima only where actually used; breaking changes major-bump the producer and update every consumer's lower bound plus code in one coordinated wave; the SciTeX-ecosystem-specific downstream/middle/upstream layering rules and `scitex-dev ecosystem sync`. Companion to `02_dependency-and-version-pinning.md`. Use when editing a `pyproject.toml` version constraint or planning a release wave.
tags: [scitex-general-ecosystem-version-pinning-rules]
---

## Version Pinning Rules

**Principle**: pin the **minimum** version that contains features you rely on. Do **not** pin upper bounds unless a known incompatibility exists. This keeps the ecosystem composable and avoids lockstep upgrades.

### Lower bound: always set it
```toml
# Good
dependencies = [
    "numpy>=1.21.0",         # we use numpy.typing, first in 1.21
    "scitex-io>=0.3.0",      # we call scitex-io.save with new dry_run= kwarg
]

# Bad
dependencies = [
    "numpy",                 # ambiguous — breaks reproducibility of CI
    "scitex-io==0.3.4",      # too tight — blocks consumers
]
```

### Upper bound: only when proven broken
- Add `,<X` **only** when a specific release is known to break, and open an issue to track.
- Prefer fixing forward (new release with `>=Y.Z`) over capping upstream.
- Never cap by default — capping a major version (`<2`) traps consumers.

### When YOU update a package, bump minima in consumers

When you cut `scitex-io 0.4.0` containing a new feature used by `scitex`:

1. In `scitex-io`: bump its own version → `0.4.0`, publish, tag.
2. In every consumer (middle + upstream + downstream that uses it via the `all` extra):
   - Bump its `scitex-io` lower bound to the new minimum that contains the feature.
   - Add a note in the consumer's CHANGELOG linking the feature used.
   - Bump the consumer's own **patch** version (feature now requires newer dep).
3. **Do not** bump minima speculatively — only when you actually use a new API.
4. **Breaking changes** (rename, signature change, removal):
   - Major-bump the producing package.
   - Update every consumer's lower bound **and** code in the same coordinated release wave.
   - Consumers should fail fast on the old minimum rather than silently accept it.

### SciTeX-ecosystem-specific rules

- **Downstream → middle/upstream**: runtime minima live only inside the **`all` extra** — the only extra that may exist ([26_the-only-extra-is-all.md](26_the-only-extra-is-all.md)). The bare install stays ecosystem-free.
  ```toml
  [project.optional-dependencies]
  all = [
      # --- SciTeX cascade ------------------------------------------
      "scitex-io[all]>=0.4.0",
      "scitex[all]>=2.24.0",
  ]
  ```
  *(Amended 2026-08-31 — this used to read `scitex = ["scitex-io>=0.4.0", "scitex[session]>=2.24.0"]`. Both halves changed: the extra is now `all`, and a leaf is listed as `scitex-<x>[all]` so its own optional deps come with it.)*
- **Middle → downstream**: minima go in the **`dev` dependency-GROUP** (plugin targets for integration tests), not runtime and not an extra.
  ```toml
  [dependency-groups]
  dev = ["scitex-dev", "pytest>=7.0", "figrecipe>=0.13.0"]  # for cascade tests
  ```
- **Upstream → everything**: minima go under **runtime** deps with matched version ranges.
  ```toml
  dependencies = [
      "scitex-io>=0.4.0",
      "scitex-stats>=0.5.0",
      "figrecipe>=0.13.0",
  ]
  ```
- **Coordinated waves**: when multiple ecosystem packages change together, bump them in one wave with matched minima so a fresh `pip install "scitex[all]"` resolves cleanly. `[all]` is what users type, so it is the resolution that has to work.
- **`scitex-dev ecosystem sync`** (or equivalent) is the canonical tool for fanning minima updates across the ecosystem. Prefer it over hand-editing.

### Quick rule of thumb

> Raise a lower bound **only** when you rely on something that version introduced. Lower it **never**. Cap an upper bound **only** when a release is proven broken.
