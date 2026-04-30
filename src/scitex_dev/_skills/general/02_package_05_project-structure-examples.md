---
name: package-examples
description: `./examples/` for a SciTeX package — runnable demos, mandatory numbered prefix (`01_<descriptive-name>.{py,sh,ipynb}`), `_out/` artefacts committed to git so users see them on GitHub, `00_run_all.sh` dispatcher, matched 1:1 by `tests/examples/test_<stem>.py`. Use SciTeX where applicable (`@stx.session`, `stx.io`, `stx.plt`); examples are free to import the umbrella `scitex`. Include agentic demos (MCP-tool prompts, Skills invocation patterns) where the package exposes those interfaces.
tags: [scitex-python, scitex-general, scitex-package, project-structure, examples]
---

# `./examples` — runnable demos

> Sibling leaves: [`./root`](02_package_01_project-structure-root.md) · [`./src`](02_package_02_project-structure-src.md) · [`./scripts`](02_package_03_project-structure-scripts.md) · [`./scripts/makefile`](02_package_04_project-structure-makefile.md) · [`./tests`](02_package_06_project-structure-tests.md)

## What goes here

- Runnable demos for each main feature.
- Every example must actually work (validated by `tests/examples/`).
- Examples are **free to import the umbrella `scitex`** — unlike `src/`, they sit at the consumer side of the cascade.
- Use SciTeX where applicable: `@stx.session`, `stx.io`, `stx.plt`.

## Mandatory numbered prefix

```
./examples/01_<descriptive-name>.{py,sh,ipynb}
./examples/01_<descriptive-name>_out/        # outputs, git-tracked
./examples/02_<another-name>.py
./examples/02_<another-name>_out/
./examples/00_run_all.sh                     # dispatcher
```

- The `NN_` prefix gives a stable execution order and makes `00_run_all.sh` a simple `for f in NN_*.py; do …; done`.
- `.py` is preferred over `.ipynb` for diffability + CI; pick `.ipynb` only when GitHub-rendering is the point.

## `_out/` artefacts — git-tracked

Each example writes to `./examples/<stem>_out/` (a sibling directory, not a subdir of the example file's stem).

- These directories are **git-tracked** so users see what the demo produces on GitHub.
- A few outputs (figures, GIFs) are linked from `README.md` as assets.
- Outputs that bloat the wheel: keep them out via the `templates/` / wheel-vs-git pattern (see [`02_package_01_project-structure-root.md`](02_package_01_project-structure-root.md#templates--wheel-vs-git-payload-separation)).
- Don't commit run-specific artefacts like `SDIR_RUN/` outputs — those are session-unique and would churn on every demo run.

## `00_run_all.sh` — dispatcher

A single-command end-to-end demo + CI regress:

```bash
#!/bin/bash
# ./examples/00_run_all.sh
set -euo pipefail
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$THIS_DIR"
for f in 0[1-9]_*.py 1[0-9]_*.py; do
    [ -f "$f" ] || continue
    echo "==> $f"
    python "$f"
done
```

## 1:1 match with `tests/examples/`

Every example file has a matching test under [`./tests/examples/`](02_package_06_project-structure-tests.md). The test's job is to confirm the example runs to completion and produces the expected `_out/` artefacts.

```
examples/01_load_save.py            →  tests/examples/test_01_load_save.py
examples/02_plot_summary.py         →  tests/examples/test_02_plot_summary.py
```

PS303 of `audit-project` flags an example without a matching test.

## Agentic demos

Where the package exposes MCP tools or Skills, the examples directory should include:

- A `.py` file showing the **direct Python API** call (e.g. `stx.io.save(...)`).
- A short prompt file or markdown demo showing the **agentic invocation** (the MCP-tool name an agent would call, the Skill phrase that should trigger it).

This lets `tests/agentic/` regress the trigger surface against real prompts.

## Quick checklist

- [ ] `./examples/00_run_all.sh` dispatcher exists
- [ ] Every demo file numbered `NN_<descriptive-name>.{py,sh,ipynb}`
- [ ] Every demo has a sibling `_out/` directory committed
- [ ] Every demo has a matching `tests/examples/test_*.py`
- [ ] Outputs linked from README are produced by an example, not hand-edited
