# CLI Convention Audit — 2026-04-25

Ecosystem-wide snapshot against `01_interface_02_cli.md` §1 (noun-verb) + §1c (catalog). Produced by `scitex-dev quality audit-cli`. Warn-only — no CLI was modified.

## Summary

| Package | Status | Warnings |
|---|---|---|
| scitex | — argparse (auditor cannot introspect) | — |
| scitex-io | ⚠ violations | 4 |
| scitex-stats | — argparse (auditor cannot introspect) | — |
| scitex-plt | ⚠ violations | 16 |
| scitex-scholar | — argparse (auditor cannot introspect) | — |
| scitex-writer | — argparse (auditor cannot introspect) | — |
| scitex-linter | — argparse (auditor cannot introspect) | — |
| scitex-cloud | ⚠ violations | 25 |
| scitex-dev | ⚠ violations | 8 |
| scitex-clew | — no console_script | — |
| scitex-container | ⚠ violations | 10 |
| scitex-dataset | ⚠ violations | 12 |
| scitex-notification | ⚠ violations | 6 |
| scitex-tunnel | ⚠ violations | 4 |
| scitex-ui | ⚠ violations | 2 |
| scitex-app | ⚠ violations | 10 |
| scitex-audio | ⚠ violations | 8 |
| scitex-db | — argparse (auditor cannot introspect) | — |
| scitex-orochi | — argparse (auditor cannot introspect) | — |
| scitex-diagram | — argparse (auditor cannot introspect) | — |
| scitex-notebook | ⚠ violations | 4 |
| scitex-template | — argparse (auditor cannot introspect) | — |
| figrecipe | ⚠ violations | 16 |
| crossref-local | — argparse (auditor cannot introspect) | — |
| openalex-local | — argparse (auditor cannot introspect) | — |

## Details

### `scitex-io`

```
warn  scitex-io: 4 warning(s)
  [§1c] main configs: 'configs' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main info: leaf token looks like a noun — transitive action implied; use '<verb>-info' (e.g. start-info) or add a sibling verb
  [§1] main mcp installation: leaf token looks like a noun — transitive action implied; use '<verb>-installation' (e.g. start-installation) or add a sibling verb
  [§1c] main skills: 'skills' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
```

### `scitex-plt`

```
warn  scitex-plt: 16 warning(s)
  [§1] main completion status: leaf token looks like a noun — transitive action implied; use '<verb>-status' (e.g. start-status) or add a sibling verb
  [§1c] main completion zsh: 'zsh' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main compose: bare transitive verb at top level — needs an object; use 'compose-<object>' or nest under a noun
  [§1] main convert: bare transitive verb at top level — needs an object; use 'convert-<object>' or nest under a noun
  [§1] main diagram info: leaf token looks like a noun — transitive action implied; use '<verb>-info' (e.g. start-info) or add a sibling verb
  [§1c] main diagram presets: 'presets' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main diagram backends: 'backends' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main diff: bare transitive verb at top level — needs an object; use 'diff-<object>' or nest under a noun
  [§1c] main fonts: 'fonts' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main gui: leaf token looks like a noun — transitive action implied; use '<verb>-gui' (e.g. start-gui) or add a sibling verb
  [§1c] main hitmap: 'hitmap' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main info: leaf token looks like a noun — transitive action implied; use '<verb>-info' (e.g. start-info) or add a sibling verb
  [§1] main mcp info: leaf token looks like a noun — transitive action implied; use '<verb>-info' (e.g. start-info) or add a sibling verb
  [§1] main reproduce: bare transitive verb at top level — needs an object; use 'reproduce-<object>' or nest under a noun
  [§1] main validate: bare transitive verb at top level — needs an object; use 'validate-<object>' or nest under a noun
  [§1c] main skills: 'skills' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
```

### `scitex-cloud`

```
warn  scitex-cloud: 25 warning(s)
  [§1] main app dev: leaf token looks like a noun — transitive action implied; use '<verb>-dev' (e.g. start-dev) or add a sibling verb
  [§1] main app current: leaf token looks like a noun — transitive action implied; use '<verb>-current' (e.g. start-current) or add a sibling verb
  [§1] main app info: leaf token looks like a noun — transitive action implied; use '<verb>-info' (e.g. start-info) or add a sibling verb
  [§1c] main app prefs: 'prefs' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main setup: leaf token looks like a noun — transitive action implied; use '<verb>-setup' (e.g. start-setup) or add a sibling verb
  [§1] main deploy: bare transitive verb at top level — needs an object; use 'deploy-<object>' or nest under a noun
  [§1] main docker ps: leaf token looks like a noun — transitive action implied; use '<verb>-ps' (e.g. start-ps) or add a sibling verb
  [§1c] main gitea: 'gitea' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main gitea login: 'login' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main gitea logout: 'logout' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main gitea status: leaf token looks like a noun — transitive action implied; use '<verb>-status' (e.g. start-status) or add a sibling verb
  [§1] main mcp installation: leaf token looks like a noun — transitive action implied; use '<verb>-installation' (e.g. start-installation) or add a sibling verb
  [§1c] main context eval: 'eval' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main context action: leaf token looks like a noun — transitive action implied; use '<verb>-action' (e.g. start-action) or add a sibling verb
  [§1] main status: leaf token looks like a noun — transitive action implied; use '<verb>-status' (e.g. start-status) or add a sibling verb
  [§1c] main logs: 'logs' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main completion: leaf token looks like a noun — transitive action implied; use '<verb>-completion' (e.g. start-completion) or add a sibling verb
  [§1c] main workspace: 'workspace' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main workspace logout: 'logout' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main sdk: 'sdk' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main sdk jobs: 'jobs' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main sdk jobs status: leaf token looks like a noun — transitive action implied; use '<verb>-status' (e.g. start-status) or add a sibling verb
  [§1] main push: bare transitive verb at top level — needs an object; use 'push-<object>' or nest under a noun
  [§1] main pull: bare transitive verb at top level — needs an object; use 'pull-<object>' or nest under a noun
  [§1c] main skills: 'skills' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
```

### `scitex-dev`

```
warn  scitex-dev: 8 warning(s)
  [§1] main ecosystem dashboard: leaf token looks like a noun — transitive action implied; use '<verb>-dashboard' (e.g. start-dashboard) or add a sibling verb
  [§1] main stats: leaf token looks like a noun — transitive action implied; use '<verb>-stats' (e.g. start-stats) or add a sibling verb
  [§1] main config: leaf token looks like a noun — transitive action implied; use '<verb>-config' (e.g. start-config) or add a sibling verb
  [§1] main rename: bare transitive verb at top level — needs an object; use 'rename-<object>' or nest under a noun
  [§1c] main skills: 'skills' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main completion: leaf token looks like a noun — transitive action implied; use '<verb>-completion' (e.g. start-completion) or add a sibling verb
  [§1] main search: bare transitive verb at top level — needs an object; use 'search-<object>' or nest under a noun
  [§1] main mcp installation: leaf token looks like a noun — transitive action implied; use '<verb>-installation' (e.g. start-installation) or add a sibling verb
```

### `scitex-container`

```
warn  scitex-container: 10 warning(s)
  [§1] main build: bare transitive verb at top level — needs an object; use 'build-<object>' or nest under a noun
  [§1] main list: bare transitive verb at top level — needs an object; use 'list-<object>' or nest under a noun
  [§1] main rollback: bare transitive verb at top level — needs an object; use 'rollback-<object>' or nest under a noun
  [§1] main deploy: bare transitive verb at top level — needs an object; use 'deploy-<object>' or nest under a noun
  [§1] main cleanup: leaf token looks like a noun — transitive action implied; use '<verb>-cleanup' (e.g. start-cleanup) or add a sibling verb
  [§1] main verify: bare transitive verb at top level — needs an object; use 'verify-<object>' or nest under a noun
  [§1] main sandbox cleanup: leaf token looks like a noun — transitive action implied; use '<verb>-cleanup' (e.g. start-cleanup) or add a sibling verb
  [§1c] main host mounts: 'mounts' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main status: leaf token looks like a noun — transitive action implied; use '<verb>-status' (e.g. start-status) or add a sibling verb
  [§1c] main env-snapshot: 'env-snapshot' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
```

### `scitex-dataset`

```
warn  scitex-dataset: 12 warning(s)
  [§1c] main openneuro: 'openneuro' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main dandi: 'dandi' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main physionet: 'physionet' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main zenodo: 'zenodo' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main figshare: 'figshare' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main openml: 'openml' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main moleculenet: 'moleculenet' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main geo: leaf token looks like a noun — transitive action implied; use '<verb>-geo' (e.g. start-geo) or add a sibling verb
  [§1c] main chembl: 'chembl' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main clinicaltrials: 'clinicaltrials' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main db stats: leaf token looks like a noun — transitive action implied; use '<verb>-stats' (e.g. start-stats) or add a sibling verb
  [§1] main completion: leaf token looks like a noun — transitive action implied; use '<verb>-completion' (e.g. start-completion) or add a sibling verb
```

### `scitex-notification`

```
warn  scitex-notification: 6 warning(s)
  [§1] cli send: bare transitive verb at top level — needs an object; use 'send-<object>' or nest under a noun
  [§1c] cli sms: 'sms' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] cli backends: 'backends' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] cli config: leaf token looks like a noun — transitive action implied; use '<verb>-config' (e.g. start-config) or add a sibling verb
  [§1] cli mcp installation: leaf token looks like a noun — transitive action implied; use '<verb>-installation' (e.g. start-installation) or add a sibling verb
  [§1c] cli skills: 'skills' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
```

### `scitex-tunnel`

```
warn  scitex-tunnel: 4 warning(s)
  [§1] main setup: leaf token looks like a noun — transitive action implied; use '<verb>-setup' (e.g. start-setup) or add a sibling verb
  [§1] main remove: bare transitive verb at top level — needs an object; use 'remove-<object>' or nest under a noun
  [§1] main status: leaf token looks like a noun — transitive action implied; use '<verb>-status' (e.g. start-status) or add a sibling verb
  [§1] main mcp installation: leaf token looks like a noun — transitive action implied; use '<verb>-installation' (e.g. start-installation) or add a sibling verb
```

### `scitex-ui`

```
warn  scitex-ui: 2 warning(s)
  [§1] main mcp-group installation: leaf token looks like a noun — transitive action implied; use '<verb>-installation' (e.g. start-installation) or add a sibling verb
  [§1c] main skills: 'skills' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
```

### `scitex-app`

```
warn  scitex-app: 10 warning(s)
  [§1] main read: bare transitive verb at top level — needs an object; use 'read-<object>' or nest under a noun
  [§1] main write: bare transitive verb at top level — needs an object; use 'write-<object>' or nest under a noun
  [§1] main list: bare transitive verb at top level — needs an object; use 'list-<object>' or nest under a noun
  [§1c] main exists: 'exists' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main delete: bare transitive verb at top level — needs an object; use 'delete-<object>' or nest under a noun
  [§1] main rename: bare transitive verb at top level — needs an object; use 'rename-<object>' or nest under a noun
  [§1] main copy: bare transitive verb at top level — needs an object; use 'copy-<object>' or nest under a noun
  [§1] main app dev-install: leaf token looks like a noun — transitive action implied; use '<verb>-dev-install' (e.g. start-dev-install) or add a sibling verb
  [§1] main mcp installation: leaf token looks like a noun — transitive action implied; use '<verb>-installation' (e.g. start-installation) or add a sibling verb
  [§1c] main skills: 'skills' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
```

### `scitex-audio`

```
warn  scitex-audio: 8 warning(s)
  [§1] audio speak: bare transitive verb at top level — needs an object; use 'speak-<object>' or nest under a noun
  [§1c] audio backends: 'backends' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] audio check: bare transitive verb at top level — needs an object; use 'check-<object>' or nest under a noun
  [§1] audio stop: bare transitive verb at top level — needs an object; use 'stop-<object>' or nest under a noun
  [§1] audio mcp installation: leaf token looks like a noun — transitive action implied; use '<verb>-installation' (e.g. start-installation) or add a sibling verb
  [§1c] audio skills: 'skills' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] audio transcribe: bare transitive verb at top level — needs an object; use 'transcribe-<object>' or nest under a noun
  [§1c] audio env-template: 'env-template' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
```

### `scitex-notebook`

```
warn  scitex-notebook: 4 warning(s)
  [§1] cli verify: bare transitive verb at top level — needs an object; use 'verify-<object>' or nest under a noun
  [§1] cli check: bare transitive verb at top level — needs an object; use 'check-<object>' or nest under a noun
  [§1] cli compile: bare transitive verb at top level — needs an object; use 'compile-<object>' or nest under a noun
  [§1] cli convert: bare transitive verb at top level — needs an object; use 'convert-<object>' or nest under a noun
```

### `figrecipe`

```
warn  figrecipe: 16 warning(s)
  [§1] main completion status: leaf token looks like a noun — transitive action implied; use '<verb>-status' (e.g. start-status) or add a sibling verb
  [§1c] main completion zsh: 'zsh' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main compose: bare transitive verb at top level — needs an object; use 'compose-<object>' or nest under a noun
  [§1] main convert: bare transitive verb at top level — needs an object; use 'convert-<object>' or nest under a noun
  [§1] main diagram info: leaf token looks like a noun — transitive action implied; use '<verb>-info' (e.g. start-info) or add a sibling verb
  [§1c] main diagram presets: 'presets' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1c] main diagram backends: 'backends' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main diff: bare transitive verb at top level — needs an object; use 'diff-<object>' or nest under a noun
  [§1c] main fonts: 'fonts' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main gui: leaf token looks like a noun — transitive action implied; use '<verb>-gui' (e.g. start-gui) or add a sibling verb
  [§1c] main hitmap: 'hitmap' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
  [§1] main info: leaf token looks like a noun — transitive action implied; use '<verb>-info' (e.g. start-info) or add a sibling verb
  [§1] main mcp info: leaf token looks like a noun — transitive action implied; use '<verb>-info' (e.g. start-info) or add a sibling verb
  [§1] main reproduce: bare transitive verb at top level — needs an object; use 'reproduce-<object>' or nest under a noun
  [§1] main validate: bare transitive verb at top level — needs an object; use 'validate-<object>' or nest under a noun
  [§1c] main skills: 'skills' not in catalog, custom dict, or Moby POS — add to .scitex/dev/cli-audit-dict.yaml or rename
```
