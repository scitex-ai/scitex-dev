---
description: |
  [TOPIC] Interface Cli Example
  [DETAILS] SciTeX CLI reference shape — canonical top-level help output that conforms to §1 (noun groups + sub-verbs, compound leaves, no bare transitive leaves).
tags: [scitex-general-interface-cli-example]
---

# Reference example — canonical shape

The example below shows the **target shape** for a SciTeX package CLI that fully conforms to §1. The current `scitex-plt` / `figrecipe` CLI still uses bare-verb leaves (`plot`, `validate`, `extract`, `compose`, …) at top level — those are §1 anti-patterns and are tracked for migration in [TODO.md](TODO.md).

```
$ scitex-plt
Usage: scitex-plt [OPTIONS] COMMAND [ARGS]...

  FigRecipe — reproducible, style-editable scientific figures via YAML recipes.

Options:
  -V, --version     Show version and exit.
  --help-recursive  Show help for all commands.
  -h, --help        Show this message and exit.

Core:
  figure create        Create a figure from a declarative YAML/JSON spec.
  figure reproduce     Reproduce a figure from a YAML recipe.
  figure compose       Compose multiple figures into one.
  figure extract       Extract plotted data arrays from a recipe.
  figure validate      Validate that a recipe reproduces its original figure.
  figure show          Show information about a recipe.
  image convert        Convert between figure formats.
  image crop           Crop an image to its content area.
  image diff           Compare two images and report pixel differences.
  image hitmap         Generate hitmap visualization from two images.
  diagram create       Create a diagram from a spec (flowchart, pipeline, etc.).
  diagram render       Render a diagram to an image.
  diagram list         List available diagrams.
  style list           List available style presets.
  style show           Show a style preset.
  style apply          Apply a style preset to a figure.
  font list            List available fonts.
  font validate        Validate a font is installed and usable.

Service:
  gui open [SURFACE]       Open the GUI editor in the browser (auto-serve).
  gui serve                Run the GUI server in the foreground (--port, --host).
  gui status               Report whether the GUI server is running.
  gui stop                 Stop the running GUI server.
  mcp start                MCP (Model Context Protocol) server.
  mcp doctor               Self-diagnose the MCP install.
  mcp list-tools           Enumerate registered MCP tools (-v|-vv|-vvv, --json).
  mcp show-installation    Print snippet for Claude Code / MCP-host config.

Diagnostics:
  doctor               Self-diagnose installation / environment.

Introspection:
  dev list-python-apis     List public Python APIs (-v|-vv|-vvv, --json).
  dev docs-build           Build the package docs (developer-facing).
  docs list                List package documentation pages.
  docs show                Show a documentation page.
  docs search              Search documentation.
  skills list              List package skills.
  skills show              Show a skill page.
  skills search            Search skills.

Shell:
  completion install       Install shell completion (--shell bash, --dry-run).
  completion status        Report whether completion is wired for this binary.
```

## Why this shape

- **Every leaf is `<noun> <verb>` or `<verb>-<noun>` compound.** No bare transitive verbs at top level — see §1 [02_subcommand-structure-noun-verb.md](02_subcommand-structure-noun-verb.md).
- **Help sections are the fixed §4a categories** (`Core` / `Data & Sync` / `Service` / `Diagnostics` / `Introspection` / `Shell` / `Other`) rendered by `CategorizedGroup` — see [10a_command-categories.md](10a_command-categories.md). Empty categories (here `Data & Sync`, `Other`) are omitted.
- **Noun groups (`figure`, `image`, `diagram`, …)** appear when a noun has 3+ sibling verbs, and are **singular** (§1d). With 1–2 actions a compound leaf (`list-python-apis`) is preferred.
- **No bare `completion` or `version` subcommands.** `--version` is a reserved flag (§1b [04_exceptions.md](04_exceptions.md)); shell completion is the `completion` noun group (`completion install [--dry-run]`, `completion status`).
- **Developer commands live under `dev`** (§11 [18_dev-subgroup-and-ecosystem-placement.md](18_dev-subgroup-and-ecosystem-placement.md)) — `dev list-python-apis`, `dev docs-build`. User-facing commands never do.
- **The browser surface is the canonical `gui` group** (§12 [19_gui-commands.md](19_gui-commands.md)): `open` / `serve` / `status` / `stop` — never `gui start` (reserved for daemonized lifecycle) or a bare `board` leaf.
- **`doctor` is the only single-token leaf.** It's an intransitive exception (§1b). `repl` / `shell` are also allowed when the package ships an interactive session; this example doesn't.
- **`mcp list-tools` follows the same `-v|-vv|-vvv` ladder** as `dev list-python-apis` — see [03_required-introspection-commands.md](03_required-introspection-commands.md).
- **No `kill` / `display` / `rm` / `enumerate` / `check`** — synonyms picked from the canonical catalog ([06_noun-verb-catalog.md](06_noun-verb-catalog.md)); `validate` over `check` (`font validate`).

## Auto-generation note

This file should ideally be auto-generated from a real package's `--help-recursive` output, not hand-maintained — see [TODO.md](TODO.md). Hand-written examples drift; generated ones can't.
