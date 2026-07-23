---
description: |
  [TOPIC] Research Project Config — f-string paths & the eval pattern
  [DETAILS] How scripts consume `CONFIG.PATH.<KEY>` f-string values: always `eval(...)` before `stx.io.{load,save,glob}`, name local variables exactly as the f-string placeholders, use `.replace("{var}", "*")` for glob semantics, and reject unbound placeholders loudly. Plus the "phantom-unused-variable" footgun (`ruff F841` / pyright deletes eval-only bindings) and its mandatory `# noqa` + comment convention, the ergonomic wrapper alternative, and the auditor rule. Split from [`02_research-project_03_project-structure-config-and-data.md`](02_research-project_03_project-structure-config-and-data.md).
tags: [scitex-scientific-research-project-project-structure-config-and-data]
---

# Config path resolution — f-strings & `eval`

Usage-side detail for the `./config/PATH.yaml` f-string convention introduced in
[`02_research-project_03_project-structure-config-and-data.md`](02_research-project_03_project-structure-config-and-data.md).
Read that leaf first for the `PATH.yaml` tree and `symlink_to` rules.

### Using f-string paths in scripts

`CONFIG.PATH.<KEY>` returns the **literal f-string** (e.g. the string `'f"./data/seizures/{patient_id}.csv"'`). The caller resolves it with `eval(...)` against local variables in scope. The convention from real research projects (e.g. neurovista):

```python
import scitex as stx

@stx.session
def main(patient_id: str = "P001", CONFIG=stx.INJECTED, logger=stx.INJECTED):
    # Single value
    df = stx.io.load(eval(CONFIG.PATH.SEIZURES_CSV))
    # → resolves f"./data/seizures/{patient_id}.csv"  using local patient_id

    # Save with discoverable symlink (auto-creates ./data/results/.../result.csv → script_out/.../)
    stx.io.save(df, "result.csv", symlink_to=eval(CONFIG.PATH.RESULTS_CLEW_DEMO))

    # Glob over a templated directory (one f-string, many matches)
    capsules = stx.io.glob(eval(CONFIG.PATH.COHORT_A.EXTRACTED).replace(
        "{capsule_id}", "*"
    ))

    # Save into a templated location (e.g. per-cohort)
    summary = {"violations": 0}
    cohort = "A"
    stx.io.save(summary, eval(CONFIG.PATH.RESULTS.COHORT_RUN), force=True)
```

Rules for f-string usage:

- **Always `eval(CONFIG.PATH.<KEY>)` before passing to `stx.io.{load,save,glob}`** — never use the raw string.
- **Wrap the script with `@stx.session`** — only the session decorator deep-merges + injects `CONFIG`.
- **Local variables must be named exactly as the f-string placeholders.** `f"...{patient_id}..."` requires `patient_id` in the call frame.
- **For glob/wildcard semantics**, replace the placeholder with `"*"`: `eval(CONFIG.PATH.X).replace("{patient_id}", "*")`. Then call `stx.io.glob(resolved_pattern)`.
- **Reject unbound placeholders** — if a `{var}` is not in scope, `eval` raises `NameError`. That's correct: it surfaces missing parameters loudly instead of silently using a stale or wrong path.

### The "phantom-unused-variable" problem

`eval(CONFIG.PATH.X)` reads `patient_id` from the call frame, but to a static analyzer (`ruff F841`, `pyright reportUnusedVariable`, `vulture`) the variable looks **unused** — it's never referenced explicitly in the source. Linters will flag it, autofixers may delete it. This is the single biggest footgun of the f-string + eval pattern.

**Mandatory convention** when defining a variable solely consumed by an eval'd path:

1. **Add a `# noqa: F841` (or pyright equivalent) suppression** at the binding site.
2. **Add a one-line comment** stating which `CONFIG.PATH.<KEY>` consumes it.

```python
@stx.session
def main(patient_id: str = "P001", CONFIG=stx.INJECTED, logger=stx.INJECTED):
    # patient_id consumed by eval(CONFIG.PATH.SEIZURES_CSV) below.
    # noqa: F841 — referenced inside f-string, invisible to static analysis.

    df = stx.io.load(eval(CONFIG.PATH.SEIZURES_CSV))
    # ↑ resolves f"./data/seizures/{patient_id}.csv"
```

Or, when the consuming line is far from the binding, repeat the suppression at the binding:

```python
patient_id = picker.next()  # noqa: F841 — see eval(CONFIG.PATH.SEIZURES_CSV)
...  # 30 lines of unrelated work
df = stx.io.load(eval(CONFIG.PATH.SEIZURES_CSV))
```

**Better alternative when available**: a wrapper function that names the bindings explicitly and avoids `eval`:

```python
# Hypothetical ergonomic wrapper (if/when scitex-io exposes it):
df = stx.io.load(stx.io.resolve(CONFIG.PATH.SEIZURES_CSV, patient_id=patient_id))
```

This makes `patient_id` a *real* function argument — visible to linters, IDEs, and refactoring tools. Prefer this form when the helper is available; fall back to `eval` + suppression comment otherwise.

**Auditor rule** (research-project mode): flag any `eval(CONFIG.PATH.*)` whose preceding ~5 lines contain a binding without a `# noqa` or `# eval` marker. The fix is to add the suppression, not to remove the variable.
