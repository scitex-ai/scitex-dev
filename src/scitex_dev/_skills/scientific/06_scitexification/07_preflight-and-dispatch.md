---
description: |
  [TOPIC] Scitexification — pre-flight rules and phase dispatch.
  [DETAILS] The universal SciTeX pre-flight checklist (Makefile SHELL,
  PATH.yaml wrapper, five injected params, symlink_to I/O, DAG file
  tips, no plt.savefig, non-descriptive source names) applied BEFORE
  writing code, plus the four-phase dispatch (read / notebook /
  repro-doc / infer) that selects stage-1 extraction. Moved verbatim
  out of 00_playbook.md.
tags: [scitexification, scitexification-preflight]
---

## Pre-flight (universal SciTeX rules)

Apply these BEFORE writing any code. They catch the recurring failure
modes that no amount of careful translation will fix later.

```
□ Makefile must NOT set `SHELL := /bin/bash`. It breaks `@stx.session`
  under `make`.
□ config/PATH.yaml: NO outer `PATH:` wrapper. Top-level keys are exposed
  directly under `CONFIG.PATH.<KEY>`; an outer wrapper produces
  `CONFIG.PATH.PATH.<KEY>` and every access site crashes with
  `AttributeError`. (See PS-PATH-001.)
□ `@stx.session` declares ALL FIVE injected params explicitly: CONFIG,
  COLORS, logger, plt, rngg. Missing one breaks DI assumptions in
  downstream stx modules.
□ Cross-stage I/O via `stx.io.save(..., symlink_to=eval(CONFIG.PATH.X))`.
  Vars consumed only by `eval(CONFIG.PATH.X)` need `# noqa: F841`.
□ For non-standard extensions (e.g. `.mmd`, `.tex` source), fall back
  to `Path(...).write_text(...)`; `stx.io.save` handles only the
  ecosystem-registered savers (see scitex-io's per-extension registry).
□ `stx.io.load(".txt")` returns `list[str]` of lines, NOT a single
  string. Iterate as-is or `"\n".join(lines)` if you need flat text.
□ Tips of the DAG (root inputs AND final outputs) MUST be FILES, not
  scripts. The final stage ends at a file saved via `stx.io.save(...)`,
  not at the script node.
□ All figures via `stx.plt` / FigRecipe so they enter the DAG as data.
  `matplotlib.pyplot.savefig()` is forbidden — it writes outside the
  session's output dir, the file is invisible to provenance tooling,
  and `make repro` silently breaks.
□ Files with non-descriptive source names (literal "output", "stdout"):
  COPY (not symlink) into a descriptive name in `data/` before stage 1.
  Clew/scitex-io resolve symlinks to target basename, so a symlink
  `result_output.txt` → `output` shows up as `output` in the DAG. A real
  copy `result_output.txt` shows clearly.
```

## Phase dispatch

Before writing stage 1, inspect `$SRC` and pick a phase. The four phases
share the same downstream (stages 1→5); only stage 1's *extraction*
differs.

```python
from pathlib import Path
src = Path(SRC)
results_dir   = src / "results"
has_results     = results_dir.exists() and any(results_dir.iterdir())
has_notebook    = bool(list(src.rglob("*.ipynb")))
# The project's OWN reproduction instructions, whatever it calls them.
REPRO_ENTRYPOINTS = ("REPRODUCING.md", "REPRODUCE.md", "reproduce.sh",
                     "run.sh", "run_all.sh", "Makefile", "Snakefile",
                     "dvc.yaml", "Dockerfile")
has_repro_doc   = (any((src / n).exists() for n in REPRO_ENTRYPOINTS)
                   or readme_has_run_commands(src))   # see note below

if has_results:
    phase = "read"        # parse existing result files — fastest
elif has_notebook:
    phase = "notebook"    # convert + execute the notebook
elif has_repro_doc:
    phase = "repro-doc"   # follow the documented reproduction recipe
else:
    phase = "infer"       # explore code/ + data/, infer the entry point
```

Notes for newcomers:

- **`repro-doc` means "the project tells you how to run it".** That may
  be a dedicated file (`REPRODUCING.md`, `reproduce.sh`), a build file
  (`Makefile`, `Snakefile`, `dvc.yaml`), a `Dockerfile`, or a README
  section. A bare `README.md` alone is too broad a signal — many
  READMEs describe the project without a runnable recipe. Count a README
  only when it contains actual run commands (a "Usage" / "Reproduce" /
  "Run" section with shell or Python commands); otherwise fall through
  to `infer`.
- **`read` grounds claims in the files the source shipped.** That is
  honest but weaker than re-running: prefer re-executing when it is
  feasible (stage 4.0 in [04_repro-clew.md](04_repro-clew.md)), and say
  in the claim's evidence which one you did.
- The order is a default, not a law. If a notebook exists *and* a
  Makefile drives it, follow the Makefile.

| Phase | Stage-1 tool |
|---|---|
| read | direct file reads — `stx.io.load(...)`, pandas / json |
| notebook | `scitex_notebook.convert_notebook(..., mode="unified")` then `subprocess.run(["python", "stage1.py"])` |
| repro-doc | follow the project's documented commands; translate container runtimes where needed (e.g. `docker run ...` → `apptainer exec ...` where no Docker daemon is available) |
| infer | inspect the source tree for `if __name__ == "__main__"`, a `main()`, or a CLI entry point; do not modify the source repo |

All four phases converge at `extract → answers/results → claims`.
