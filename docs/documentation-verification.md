# Scoped documentation verification

`scitex_dev.verify_docs_and_skills(package_path, *, documents=None)` performs
static, read-only checks against a selected source checkout. It does not export
skills, look up user skill caches, import audited modules, execute examples or
launch subprocesses.

```python
from pathlib import Path
from scitex_dev import verify_docs_and_skills

report = verify_docs_and_skills(
    Path("."), documents=[Path("README.md")]
)
```

Without `documents`, the scope is `README.md` plus
`src/*/_skills/**/*.md`. Explicit document paths must stay inside the package
root; missing/unreadable files, invalid UTF-8, malformed Python fences and
unreadable/unparseable referenced source are reported as failures.

Top-level closed Markdown fences labeled exactly `python` or `py` are parsed
with Python's AST. Fences nested in lists/quotes are outside this parser's scope.
Imports referring to local `src/` modules are checked for an existing parsable
module and direct function/class definition or source submodule. Explicit
top-level `from` re-exports are followed through local source, including aliases
and relative source imports. A regular package takes precedence over a
same-named module, matching Python's file finder. Missing local targets and
unreadable/unparseable source are reported as failures.

This proves source declarations, not runtime importability. Traversal stops
after 32 references; cycles, longer chains, multiple or conditional bindings,
assignments, star imports, dynamic attributes and external targets remain
explicitly unverified. Relative imports in Markdown examples also remain
unverified because the example's package context is not established. Source
symlinks cannot escape the selected root.

The current source also checks argument shapes for plain local functions
identified by explicit imports in the same example, including local re-exports.
Missing arguments, unsupported keywords and invalid positional/keyword use are
issues. Accepted calls appear in `checked_scope["calls"]`. Defaults, annotations
and function bodies are never evaluated. Decorated functions, constructors,
nested Python scopes, reassigned aliases and `*args`/`**kwargs` expansion remain
unverified. This checks call shape, not argument types, values or results.
See `src/scitex_dev/_ecosystem/_skills/_source_calls.py` and the behavioral
controls in `tests/scitex_dev/_ecosystem/_skills/test__source_calls.py`.
Check the installed version and report fields before assuming this extension
is available in an older installation.

Prose, RST, other languages, example results, CLI/MCP/Web API behavior and
exported skill drift are outside this helper's coverage. Continue the
five-interface audit for those checks.

The result retains the legacy `issues`, `stale_files`, `skills_stale`,
`readme_version_match` and `status` keys. `checked_scope` records documents,
Python block count, verified import references and checked calls; `unverified` and
`limitations` identify the remaining coverage. `export_staleness` is always
`not_checked`. `skills_stale` is `True` for known packaged-skill failures,
`False` only when its selected static scope has no outstanding unknowns, and
`None` when absent or incomplete. It never claims an export-cache comparison.

Only an explicit `Version: X` README line is compared with a literal
`[project].version`. A README does not need a literal version. The nullable
`readme_version_match` is accompanied by `readme_version_check` (`match`,
`mismatch`, `not_present`, `not_checked` or `failed`); invalid metadata during
an attempted comparison remains a visible failure.

`status` is `needs_update` for definite failures, `incomplete` for unverified
references or no Python blocks, otherwise `ok` within the reported static
scope. No status means complete documentation or ecosystem drift verification.

The example above imports `Path` from the standard library and
`verify_docs_and_skills` through Dev's lazy public facade. With the current
static resolver, checking this guide against Dev's own source reports these
bindings as unverified and returns `incomplete`, with no detected issues.
Keep that coverage limit visible. The owning behavioral tests and installed
interface checks establish runtime behavior separately.
