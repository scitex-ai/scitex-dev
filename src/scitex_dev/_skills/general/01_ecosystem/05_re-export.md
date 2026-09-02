---
description: |
  [TOPIC] Ecosystem Re Export
  [DETAILS] Re-export convention that lets `scitex.<name>.X` and `scitex_<name>.X` always resolve to the same object — the `scitex.<name>` umbrella subpackage thin-re-exports the standalone `scitex_<name>` public API, with a lazy-import guard so unused optional deps never trigger import errors, a stable `__all__` contract, and no original logic in the bridge. Prevents the common bug where agents read one form in docs and the other in examples, getting different runtime behaviour. Use when setting up a new scitex-* standalone + its bridge, adding a new public symbol, or debugging why `scitex.X.Y` differs from `scitex_X.Y`.
tags: [scitex-general-ecosystem-re-export]
---

# Umbrella Re-Export Convention

## Why re-export

Agents and humans discover features through **both** namespaces:

- `scitex.path.find_git_root` — the ecosystem-wide umbrella.
- `scitex_path.find_git_root` — the standalone leaf package.

These MUST resolve to the **same** object. If they drift, searchability, docs,
and example chains break silently (`stx.path.find_git_root()` falls back to a
shim while the real implementation only exists in the standalone).

## Where to re-export

Each umbrella bridge module lives at `src/scitex/<name>/__init__.py` inside the
`scitex-python` umbrella. The bridge is **thin**: it re-exports from the
standalone and adds only a lazy-import guard that raises a clear
`ImportError` when the standalone isn't installed.

Prefer explicit re-exports (named imports + `__all__`) over `from X import *`
so the public surface is grep-able.

## Separation of concerns

| Layer | Owns | Must NOT |
|---|---|---|
| Standalone `scitex_<name>` | Implementation, tests, version, API stability | Depend on the umbrella |
| Umbrella `scitex.<name>` bridge | Thin re-export + `ImportError` guard | Ship implementation; override behaviour |

The umbrella NEVER implements logic. If the standalone isn't installed, the
bridge raises `ImportError` with a pointer to `pip install "scitex[all]"` —
or to the leaf directly, `pip install scitex-<name>`. Never a per-feature
extra: `all` is the only extra that exists
([26_the-only-extra-is-all.md](26_the-only-extra-is-all.md)). This is the
hard rule; see `01_ecosystem/03_modules-and-standalone-packages.md` §8.

## Umbrella = coordinator + namespace ONLY (hard rule)

"No logic" generalizes: the umbrella also holds **no linter rules, no skills,
no per-tool MCP bridges, and no redundant top-level alias** when a natural
`scitex.<owner>.<x>` path already exists. Every in-tree dir holding real
implementation is factored to its owning standalone, leaving only a thin alias.

- Logic dir → owner + thin alias (owner absorbs logic+skills and RELEASES first,
  then umbrella aliases + bumps pin). e.g. media→scitex_etc.media,
  cloud/module/project→scitex_hub.
- Linter rules live in scitex-dev (`scitex_dev.linter._rules`, gated
  `requires="scitex"`), surfaced via `scitex.dev.linter` — NOT a
  `_linter_plugin.py` entry-point in the umbrella.
- No redundant top-level alias (dropped `scitex.linter`; channel is
  `scitex.dev.linter`).
- MCP = ONE registry-mounting entrypoint (`src/scitex/_mcp/`) that mounts every
  peer FastMCP with brand-prefix + tool renames, skipping optional peers
  gracefully. NO per-package `register_<pkg>_tools` bridge files.

### Unreleased peers stay OUT of `all`

*(Amended 2026-08-31. This section used to say "pin only in the targeted
extra (`[cloud]`/`[hub]`/…), never `[all]`/`[dev]`". There is no longer a
targeted extra to pin into —
[26_the-only-extra-is-all.md](26_the-only-extra-is-all.md) permits `all`
and nothing else. The mechanism the old rule leaned on is gone; the hazard
it guarded against is not.)*

For a heavy or **unreleased** owner (e.g. scitex-hub), simply do not list it
— not in `dependencies`, not in `all`, and there is nowhere else to put it.
Base `import scitex` works without it, the bridge raises the install-hint
stub on access, and the cross-package import test skips it (peer absent in
CI → matrix green without releasing the heavy owner).

**Corollary, and it hardens under the new rule**: do NOT release the
umbrella while `all` pins an unreleased owner version. Previously a bad pin
was quarantined inside an extra almost nobody installed; now it sits in the
one extra everybody installs, so the same mistake breaks every user rather
than a few.

**Heaviness alone is not a reason to omit.** The old rule let "heavy" and
"unreleased" share one escape hatch. Only *unreleased* justifies omission
now — a released-but-heavy owner belongs in `all`, because `[all]` is the
only thing anyone types and a package missing from it is invisible.

Source: 2026-05-31 umbrella-thinning campaign (scitex-python #308 + #309,
scitex-dev 0.16.0, scitex-etc 0.2.0).

## When NOT to re-export

- Underscore-prefixed helpers (`_internal_foo`) — private to the standalone.
- Test utilities under `scitex_<pkg>.testing._*` — not public API.
- APIs that intentionally don't exist in the umbrella namespace (experimental,
  deprecated, or standalone-only CLI plumbing).
- Symbols that may not exist in the pinned PyPI release — guard with
  `try/except ImportError` and provide a minimal shim (see scholar pattern
  below).

For the concrete bridge implementations — the `scitex.scholar`
explicit-named-re-export pattern, the release-gate `__all__`-diff check,
and the alternative `sys.modules` aliasing (template pattern) with its
tradeoff table and when-to-choose-which guidance — see
[20_re-export-patterns.md](20_re-export-patterns.md).

## Note — two different "re-export" mechanisms

This skill covers the **umbrella ↔ standalone** bridge: `scitex.<name>` re-exports `scitex_<name>` so docs and examples written in either namespace resolve to the same object.

The **library cascade** in [`01_ecosystem/01_upstream-and-downstream.md`](01_upstream-and-downstream.md) (`stx.io.save → scitex-io.save → figrecipe.save` via plugin registry) is a *different* mechanism — middle layers wrap downstream behaviour through entry-point plugins, not via thin `from … import …` re-exports. Don't confuse the two: the umbrella bridge is one-to-one (no logic), the cascade is many-to-one (dispatcher + plugin handlers).

## Quick Checklist (re-export bridges)

- [ ] `scitex.<name>` and `scitex_<name>` have identical `__all__` (release-gate Python check passes).
- [ ] Bridge file contains no logic — only `from scitex_<name> import …`, optional fallback shims, and `__all__`.
- [ ] The scitex umbrella's `all` extra installs `scitex-<name>` (not just transitive third-party deps) — and lists it as `scitex-<name>[all]`. There is no per-name extra ([26](26_the-only-extra-is-all.md)).
- [ ] When the standalone isn't installed, importing the bridge raises `ImportError` with a `pip install "scitex[all]"` (or `pip install scitex-<name>`) hint — never a per-feature extra, never silent `None` exports.
- [ ] New-in-next-release standalone symbols are guarded with `try: from scitex_<name> import X / except ImportError: <minimal shim>` so the umbrella imports cleanly against the pinned PyPI release.
- [ ] If the package needs deep submodule paths preserved, `sys.modules` aliasing pattern is used instead of named re-exports — and the migration plan to delete the alias is documented.
- [ ] Tests inside the standalone repo import via `scitex_<name>.…`, never `scitex.<name>.…`.
