---
description: |
  [TOPIC] scitex-linter CLI Reference
  [DETAILS] Top-level subcommands of `scitex-linter` — check-files, format-files, lint-and-run, list-rules, list-rules-all, mcp, completion helpers.
tags: [scitex-linter-cli-reference]
---

# CLI Reference

`scitex-linter` is the entry point installed by `pip install scitex-linter`.

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
| `check-files`   | Check Python files for SciTeX pattern compliance        |
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

## Configuration precedence

```
1. Explicit CLI flags
2. ./pyproject.toml [tool.scitex_linter]
3. ./config.yaml (project-local)
4. $SCITEX_LINTER_CONFIG (path to a YAML file)
5. ~/.scitex/linter/config.yaml (user-wide)
6. Built-in defaults
```

## Examples

```bash
scitex-linter check-files src/
scitex-linter list-rules --json
scitex-linter format-files path/to/file.py
scitex-linter mcp list-tools
```

See `10_cli-reference.md` for prior detailed reference.
