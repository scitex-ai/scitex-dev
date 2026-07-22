---
description: |
  [TOPIC] Compat and refactor drift — nothing was edited, but what the code references changed
  [DETAILS] Recipes §5, §9 and §12 of the failure playbook: optional-dependency guards plus the numpy 2 bool-identity and pandas ≥ 2.2 dtype-breadth breakages, local-state path migration invalidating substring assertions in tests (the silent twin of the packaging §8 class-action), and a Click subcommand rename desyncing test invocations through a deprecated-redirect that exits 2. Triage table in the sibling `01_failure-playbook.md`; the packaging counterpart is `05_packaging-and-release-failures.md`. Use when a test or guard broke in a file nobody touched.
tags: [scitex-general-quality-compat-drift]
---

# Compat and Refactor Drift

Recipes reached from the triage table in
[01_failure-playbook.md](01_failure-playbook.md). Section numbers are the
playbook's originals, so a cross-reference elsewhere in the tree still resolves.

Every failure here is one shape:

> **The code was never edited, but what it references changed.**

The change may be upstream (numpy 2 altered what `np.any()` *is*; pandas 2.2
renamed a dtype; an optional dependency is simply absent) or our own (a
local-state layout migration, a CLI rename). Either way the edit was correct
and the breakage lands somewhere nobody touched — almost always a test, which
is why these surface as red CI on a diff that looks unrelated. The counterpart
class — where nothing in-tree broke but the published artifact is wrong — is
[05_packaging-and-release-failures.md](05_packaging-and-release-failures.md).

## 5. Optional-dep guards + numpy 2 + pandas compat

### 5a. Optional imports

```python
try:
    import plotly
except ImportError:
    plotly = None

def _is_plotly_figure(obj) -> bool:
    if plotly is None:
        return False
    return isinstance(obj, plotly.graph_objs.Figure)
```

Same for `pandas`, `xarray`, `PIL.Image`, `torch`, `seaborn`. Bare `isinstance(obj, plotly.graph_objs.Figure)` crashes with `'NoneType' has no attribute 'graph_objs'` when the dep isn't installed.

### 5b. numpy 2 bool identity

`np.any()`, `np.all()`, and similar reductions return `np.True_` / `np.False_` on numpy 2+. `np.True_ is not True`. Coerce at return:

```python
def is_listed_X(obj, types) -> bool:
    ...
    return bool(np.any(conditions))
```

Probe: `grep -rn 'return np\.\(any\|all\|bool_\)' <repo>/src/`.

### 5c. pandas dtype breadth

Don't hardcode `"object"` when checking column dtypes. pandas ≥ 2.2 uses `str`, `string`, `string[python]`. Prefer try/except:

```python
try:
    unnamed = obj.columns.str.contains("^Unnamed")
except (AttributeError, TypeError):
    unnamed = None
if unnamed is not None and unnamed.any():
    obj = obj.loc[:, ~unnamed]
```

## 9. Local-state path migration breaks tests (silent twin of §8)

§8 — the implicit-transitive-dep class-action — lives in
[05_packaging-and-release-failures.md](05_packaging-and-release-failures.md).
The *same* migration sweep produces this second, quieter failure.

**Symptom.** Local pytest passes; CI Test fails with assertions like
`assert "scitex-dataset" in str(path)` because the resolved path is now
`<scitex_dir>/dataset/runtime/datasets.db` — no `scitex-` prefix anywhere.

**Root cause.** Migrating to
`scitex_config._ecosystem.local_state.{path,runtime_path,user_path}`
changes the layout from `~/.cache/scitex-<pkg>/...` or
`~/.scitex/<full-pkg-name>/...` to the canonical
`<scitex_dir>/<pkg-short>/runtime/...` (where `pkg-short` strips the
`scitex-` prefix). Tests that asserted the old substrings now fail.

**Fix recipe.**

- Replace `assert "scitex-<pkg>" in str(path)` with semantic checks
  against the new layout: `assert "<pkg-short>" in s and "runtime" in s`,
  or construct the expected path via
  `local_state.runtime_path("<pkg-short>", "...")` rather than asserting
  string substrings.
- Canonical fixups: scitex-dataset `2190783`, scitex-container `8724740`.

## 12. Click subcommand rename desyncs tests

**Symptom.** Click CLI tests exit with code 2 ("usage error") because
``runner.invoke(cli, ["send", ...])`` references the old command name
after a refactor renamed it to ``send-notification``.

**Root cause.** A package introduces a deprecated-redirect for old
command names:

```python
cli.add_command(_deprecated_redirect("send", "send-notification"))
```

The redirect prints a usage error and exits 2 (correctly — operators
shouldn't keep using the old name). But test code that still invokes
``["send", ...]`` hits this exit-2 path and asserts ``exit_code == 0``.

**Fix.** Update the test invocations to the new names. Caught for
scitex-notification on 2026-04-28: send→send-notification,
sms→send-sms, config→show-config, backends→list-backends.

**Followup rule** (not yet codified): every Click command rename
should sweep `tests/` for the old literal at the same time. Could
codify as `E5G2_test_uses_renamed_cli` if this pattern recurs.
