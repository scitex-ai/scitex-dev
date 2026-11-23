# Building documentation

`scitex_dev.build_docs` builds one named package or every package in the local
legacy discovery mapping. It uses the package's Sphinx source, found by walking
up from its resolved root to a project marker and checking `docs/sphinx/conf.py`.
A missing source returns a package-level `{"error": "No Sphinx source found"}`.
An unknown named package raises `LookupError` before any build starts.

```python
from pathlib import Path
from scitex_dev import build_docs

results = build_docs(
    package="scitex-io", output_dir=Path("/owned/docs-output"),
    formats=["html", "json"],
)
```

The return value is nested by package and builder. Successful builder entries
are output-path **strings**. `RuntimeError` and `FileNotFoundError` raised during
a builder call become that builder's `{"error": ...}` entry, and the next format
is attempted. Missing Sphinx is such a per-format error, not a global install
exception from `build_docs`. Inspect each entry; the outer dict is not a success
flag. Successful formats remain available if another format fails. Source-lookup
errors and other exception types can still propagate.

Without `output_dir`, outputs use the discovered source's `_build/html` and
`_build/json`. With an override, the builder name is appended, as in
`/owned/docs-output/html` and `/owned/docs-output/json`. The default formats list
contains only `html`. The lower-level `build_sphinx` accepts one output directory
and raises its build errors directly; do not confuse its contract with the
per-format aggregation in `build_docs`.

Sphinx executes `conf.py` and its configured extensions. Package-root fallback
can also import provider code. These build operations execute code and write
outputs; they are not static documentation checks. The wrapper invokes
`python -m sphinx -b BUILDER -q ...` with its existing 120-second default timeout.
`-q` is quiet mode, not `-W`: a successful return does not establish that warnings
are absent. Strict CI checks, selected content assertions and source/version
binding remain separate evidence. Neither a build nor a correct local HTML/JSON
file establishes which artifact an installed wheel or live host serves.

**Displayed API defaults**

The project's Sphinx configuration preserves source expressions in displayed
function defaults. For example, `rotate_all` shows `source_path=CREDENTIALS_PATH`
instead of the documentation builder's absolute home path. In the owning
`src/scitex_dev/_creds/_rotate.py`, that constant is computed at module import
from `Path.home() / ".claude" / ".credentials.json"`. The display setting does
not change the runtime default or credential access behavior. The bundled
signature is checked by
`tests/integration/test_sphinx_source_defaults.py`; source, generated output,
installed resources and live serving still need their separate checks.

**CLI boundaries**

`scitex-dev docs get [PAGE_NAME]` reads Dev's pages. Its positional argument is
not a package selector. Use the owning leaf's corresponding page commands for
that leaf's docs. `scitex-dev docs get` lists available Dev pages; `--help` shows
the supported page/format options. This Dev CLI does not register `docs build`;
use the Python API above to build. Ecosystem-wide `docs search` is a separate
index operation with its own documented coverage limits.

Owners: `src/scitex_dev/_docs/docs.py::build_docs`,
`src/scitex_dev/_core/builder.py::build_sphinx`,
`src/scitex_dev/_core/discovery.py::get_sphinx_source`, and the shared
`_core/dispatch` plus `_cli/_docs_cmds.py` registration. Existing controls live in
`tests/scitex_dev/_docs/test_docs.py` and
`tests/scitex_dev/_cli/test__docs_cmds.py`. These checks do not qualify all builder
extensions, timeout/error variants, arbitrary provider configuration, publication
or served content.
