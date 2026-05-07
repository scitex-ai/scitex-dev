---
description: |
  [TOPIC] Repository Quality
  [DETAILS] Release-gate repository quality checklist for every SciTeX package — AGPL-3.0-only licence + the Four Freedoms (see `01_ecosystem_07_license-and-cla.md` for the full SPDX/CLA policy), README rules (no `import scitex as stx`, no trailing ywatanabe@ signature), `_builtin_handlers.py`/fallback-verification hygiene, skills-authoritative rule (no out-of-band docs in `docs/` duplicating `_skills/`), GitHub repo config (topics, default branch, branch protection), and allowlist checks before `git push` / PyPI release. Use as the final sign-off before any `vb release`.
tags: [scitex-general-package-quality]
---

# Repository Quality (SciTeX)

## SciTeX-Specific README Rules

- **"Part of SciTeX" section** with Four Freedoms blockquote
- **Use `import scitex`** (not `import scitex as stx`) in all examples
- **Footer**: SciTeX icon only — do NOT include `ywatanabe@scitex.ai` (community project)

## Licensing

- AGPL v3.0 (`license = "AGPL-3.0-only"`) is required for every SciTeX ecosystem package.
- See [01_ecosystem_07_license-and-cla.md](01_ecosystem_07_license-and-cla.md) for the full ecosystem policy: SPDX/PEP 639 specifics, the CLA workflow template, the `signatures/cla.json` shape gotcha, and bootstrap + audit recipes.

## Documentation Accuracy (SciTeX-Specific)

- **Verify documentation claims against the source of truth in the package, not just the README.** For each claim (supported formats, available flags, registered tools), open the actual registration/dispatch code in `src/` and confirm the claim matches.
- **Skills are authoritative for AI agents** — keep `src/<pkg>/_skills/` as the single source of truth; exported copies under `~/.claude/skills/scitex/<pkg>/` are refreshed via `scitex-dev skills export`.

## GitHub Setup (SciTeX Packages)

- Add `scitex` keyword as a topic for ecosystem discoverability
- CLA workflow with `allowlist: bot*,ywatanabe1989`

## Codified pyproject.toml lint (run before any release)

`scitex-dev` ships ``scitex_dev._pyproject_lint`` — a unit-tested AST-aware
linter that catches the regressions we've hit in the wild. Run it on
the package you're about to release:

```bash
python -c "from scitex_dev._cli_quality import lint_pyproject_cli;
import sys; sys.exit(lint_pyproject_cli('.'))"
```

Or invoke the ecosystem-wide sweep (matches the nightly
``quality-audit.yml`` workflow):

```bash
python ~/proj/scitex-dev/scripts/quality/audit_ecosystem.py
```

Rules (each has a stable id + unit test in
``tests/test_pyproject_lint.py``):

| Rule | Severity | Catches |
| ---- | -------- | ------- |
| ``E5C5_implicit_deps`` | CRITICAL | src imports an ecosystem dist that pyproject doesn't declare. AST-aware: ``try/except ImportError`` (any depth) and ``if TYPE_CHECKING:`` count as guards. |
| ``E5C9_skill_bundling`` | HIGH | ``_skills/`` on disk but build won't ship it (setuptools needs explicit ``package-data``; hatchling default is inclusive) OR no ``[project.entry-points."scitex_dev.skills"]`` registration. |
| ``E5C10_duplicate_table`` | HIGH | Same TOML table declared twice. Setuptools silently drops the first; tomllib refuses outright. |
| ``E5C11_invalid_pep639_license`` | MEDIUM | ``license`` is anything but the SPDX expression ``"AGPL-3.0-only"``. |
| ``E5L1_dirty_release_state`` | LOW | pyproject ↔ git tag ↔ PyPI version mismatch. |

Failure → fix the underlying issue, do NOT add to an allowlist. Each
finding ships with a ``fix_hint`` showing the exact pyproject edit.

The lint is *the source of truth* for ecosystem invariants. When a new
regression is discovered, the response is to add a rule + unit test —
not to remind the agent in conversation.

## Code-pattern lint (`scitex-dev linter`)

`pyproject_lint` above checks the *package shape*. For anti-patterns
inside the **code** (e.g. `np.save` instead of `stx.io.save`,
`scatter(..., s=10)` style overrides, `@stx.session` examples missing
INJECTED params), use `scitex-dev linter`:

```bash
scitex-dev linter check-files src/<pkg>                  # files in this package
scitex-dev linter sweep --package <pkg> --strict         # README + docs sweep, CI gate
```

Rules are **owned by the package whose API they enforce** (figrecipe
ships its own `STX-P*` / `STX-FM*` rules), and `scitex-dev linter`
aggregates them via the `scitex_dev.linter.plugins` entry point. Add a new
rule by writing a `get_plugin()` in your package's `_linter_plugin.py` —
see [`01_ecosystem_08_linter-plugins.md`](01_ecosystem_08_linter-plugins.md)
for the contract, the `requires=` runtime gate, doc-block linting
(`.md`/`.rst`/`.ipynb`), and the soft-migration window from
`scitex-linter`.
