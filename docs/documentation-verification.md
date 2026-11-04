# Scoped documentation verification

`scitex_dev.verify_docs_and_skills(package_path, *, documents=None)` performs
static, read-only checks against a selected source checkout. It does not export
skills, look up user skill caches, import audited modules, execute examples or
launch subprocesses.

```python
from pathlib import Path
from scitex_dev import verify_docs_and_skills

report = verify_docs_and_skills(
    Path("."), documents=[Path("docs/guide.md"), Path("README.md")]
)
```

Without `documents`, the scope is `README.md` plus
`src/*/_skills/**/*.md`. Explicit document paths must stay inside the package
root; missing/unreadable files, invalid UTF-8, malformed Python fences and
unreadable/unparseable referenced source are reported as failures.

Top-level closed Markdown fences labeled exactly `python` or `py` are parsed
with Python's AST. Fences nested in lists/quotes are outside this parser's scope.
Imports referring to local `src/` modules are checked for an existing parsable
module and direct function/class definition or source submodule. This proves
source declarations, not runtime importability. External modules, star and
relative imports, re-exports, assignments, conditional and dynamic bindings
remain explicitly unverified. Prose, RST, other languages, call signatures,
example results, CLI/MCP/Web API behavior and exported skill drift are outside
this helper's coverage. Continue the five-interface audit for those checks.

The result retains the legacy `issues`, `stale_files`, `skills_stale`,
`readme_version_match` and `status` keys. `checked_scope` records documents,
Python block count and verified import references; `unverified` and
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
