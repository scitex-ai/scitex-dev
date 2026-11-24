---
description: |
  [TOPIC] scitex-dev linter CLI Reference
  [DETAILS] Top-level subcommands of `scitex-dev linter` — validate-files, format-files, lint-and-run, list-rules, list-rules-all, mcp, completion helpers.
tags: [scitex-dev-linter-cli-reference]
---

# CLI Reference

`scitex-dev linter` is the entry point installed by `pip install scitex-dev`.

The standalone compatibility entry point renders the same `scitex-dev linter`
usage and examples. Subcommands appear once in example paths; mounting the
group under another CLI prefix retains that prefix.

## Top-level options

| Flag                | Purpose                                                |
|---------------------|--------------------------------------------------------|
| `-V / --version`    | Show version and exit                                  |
| `--help-recursive`  | Show help for the root and every subcommand            |
| `--json`            | Emit machine-readable JSON output where supported      |
| `-h / --help`       | Show help                                              |

## Lint / format

| Command         | Purpose                                                 |
|-----------------|---------------------------------------------------------|
| `validate-files`   | Check Python files for SciTeX pattern compliance        |
| `format-files`  | Auto-fix SciTeX pattern issues in Python files          |
| `lint-and-run`  | Lint then execute a Python script                       |

## Rules / introspection

| Command            | Purpose                                                |
|--------------------|--------------------------------------------------------|
| `list-rules`       | List all built-in SciTeX lint rules                    |
| `list-rules-all`   | List all rules, including plugin-supplied ones         |
| `list-python-apis` | List the public Python API surface                     |

## MCP / completion

| Command                    | Purpose                                          |
|----------------------------|--------------------------------------------------|
| `mcp`                      | MCP (Model Context Protocol) server management   |
| `completion`               | Shell tab-completion management                  |
| `show-completion-bash`     | Print the bash completion script                 |
| `show-completion-zsh`      | Print the zsh completion script                  |
| `show-completion-status`   | Show shell completion installation status        |

## Configuration sources and limits

`linter.config.load_config(start_path)` resolves settings in this order:

1. `SCITEX_DEV_LINTER_*` environment values (legacy `SCITEX_LINTER_*` aliases).
2. The first applicable `pyproject.toml` table found walking upward from the
   target: `[tool.scitex-dev.linter]`, with `[tool.scitex-linter]` as a deprecated
   fallback when the canonical table is empty or absent.
3. `LinterConfig` defaults.

The canonical TOML key uses `scitex-dev`, not `scitex_dev`. The current settings
loader does not read `./config.yaml`, `SCITEX_DEV_LINTER_CONFIG`, its legacy
counterpart, or `~/.scitex/dev/linter/config.yaml`. YAML settings support remains
an implementation gap; those paths must not be presented as working fallbacks.
The separate `.scitex/dev/config.yaml` `project-type` reader still applies its
existing research-type rule and capability requirements.

Command flags have their command-specific meanings. In particular,
`validate-files --severity` controls its reporting filter and defaults to
`info`; it does not derive that filter from `LinterConfig.severity` or the
severity environment setting. That consumption gap remains unresolved.
No rule, mandatory provider, exemption or exit policy changes here.

Sources: `linter/config.py`, `linter/_project_type.py` and
`linter/_cmd_check.py::_do_check`. Existing configuration/path controls:
`tests/scitex_dev/linter/test__source_helpers.py` and
`test_config_import_severity_promotion.py`.

## Examples

```bash
scitex-dev linter validate-files src/
scitex-dev linter list-rules --json
scitex-dev linter format-files path/to/file.py
scitex-dev linter mcp list-tools
```

See `10_cli-reference.md` for prior detailed reference.
