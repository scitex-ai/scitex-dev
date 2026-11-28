---
description: |
  [TOPIC] Interface Cli Required Introspection
  [DETAILS] SciTeX CLI required introspection commands — `dev list-python-apis` and `mcp list-tools` with `-v|-vv|-vvv` verbosity levels, `completion install/status`. Mandatory on every package CLI for parity with sibling packages.
tags: [scitex-general-interface-cli-required-introspection-commands]
---

# §1a. Required introspection commands

Every `scitex-*` package CLI **must** expose two introspection commands so that humans and agents can discover the package's surface without reading source.

## Commands

| Command              | Lists                                       | Section anchor                                                         |
|----------------------|---------------------------------------------|------------------------------------------------------------------------|
| `dev list-python-apis` | Public Python API (`__all__`)             | this file + [03_interface/01_python-api/SKILL.md](SKILL.md) |
| `mcp list-tools`     | MCP tools registered by the package         | this file + [03_interface/03_mcp/SKILL.md](SKILL.md)        |
| `skills {list, get, install}` | Bundled agent-facing skills (markdown leaves under `_skills/<pkg>/`) | this file + [03_interface/04_skills/SKILL.md](SKILL.md) |
| `completion install` / `completion status` | Wires up / reports bash/zsh/fish tab-completion. **Required** — without it, every scitex-* CLI ships without working `<TAB>` completion (the 2026-05-06 scitex-hpc symptom). `completion install --shell bash` must source the cached completion script into the user's shell rc; `completion install --dry-run` prints the target rc file + script without writing (retires the old `print-shell-completion`). | §1b [04_exceptions.md](04_exceptions.md) |

All follow the §1 noun-verb grammar:

- `dev list-python-apis` — `dev` noun group (§11 [18_dev-subgroup-and-ecosystem-placement.md](18_dev-subgroup-and-ecosystem-placement.md)), `list-python-apis` compound-leaf verb. The legacy top-level `list-python-apis` mount stays as a Phase W warn-forward alias (§5 [11_deprecation.md](11_deprecation.md)) during migration.
- `mcp list-tools` — `mcp` noun group, `list-tools` compound-leaf verb. (`tool` is a noun in the §1d catalog; `list-tools` bakes in the object.)
- `completion install` — `completion` noun group + `install` verb (§1b [04_exceptions.md](04_exceptions.md)).

## Verbosity convention — `-v` / `-vv` / `-vvv`

Both commands accept the same `-v` ladder. Each level **adds** information; it does not replace prior levels. `--verbose` is the long-form alias (consistent with §2 universal flags).

| Level     | `list-python-apis`                | `mcp list-tools`                                            |
|-----------|-----------------------------------|-------------------------------------------------------------|
| (default) | names only                        | tool names only                                             |
| `-v`      | + signatures                      | + signature (arg names + types)                             |
| `-vv`     | + docstrings (one-line summary)   | + docstring (one-line summary)                              |
| `-vvv`    | + full docstring + source path    | + full docstring + source module path + JSON-schema arg spec |

### Examples

```bash
$ scitex-io dev list-python-apis
save
load
load_configs
register_saver
…

$ scitex-io dev list-python-apis -v
save(obj, path: str | Path, **kwargs) -> Path
load(path: str | Path, **kwargs) -> Any
…

$ scitex-io dev list-python-apis -vv
save(obj, path: str | Path, **kwargs) -> Path
    Save any object to disk; format inferred from extension.
…

$ scitex-io mcp list-tools
io_save
io_load
io_list_formats
io_skills_list
io_skills_get

$ scitex-io mcp list-tools -v
io_save(obj: Any, path: str) -> dict
io_load(path: str) -> dict
…

$ scitex-io mcp list-tools -vv
io_save(obj: Any, path: str) -> dict
    Save any object via scitex-io.save(); returns {path, format, bytes}.
…
```

## Required flags on these commands

In addition to the verbosity ladder, both must accept (per §2 [08_universal-flags.md](08_universal-flags.md)):

- `--json` — machine-readable output. Replaces the human format with a JSON array of objects whose fields scale with the same `-v` ladder.
- `-h`, `--help` — usage with at least one example.

## Why these are mandatory

- **Discoverability without source dives** — agents and humans can list the surface in one command per concern (Python or MCP).
- **Parity check** — `list-python-apis -v` and `mcp list-tools -v` together let the auditor (§1e [07_audit-cli.md](07_audit-cli.md)) confirm CLI ↔ MCP ↔ Python parity (§7 [13_mcp-parity.md](13_mcp-parity.md)).
- **Stable contract** — verbosity ladder is the same across all `scitex-*` packages so users don't relearn flags.

## Audit hooks

The §1e auditor should verify:

- [ ] `<cli> dev list-python-apis` exists and exits 0 (legacy top-level `list-python-apis` allowed only as a Phase W alias).
- [ ] `<cli> dev list-python-apis -v|-vv|-vvv` produce monotonically more output (each level ⊇ previous).
- [ ] `<cli> mcp list-tools` exists and exits 0.
- [ ] `<cli> mcp list-tools -v|-vv|-vvv` follow the same monotonic ladder.
- [ ] Both commands honor `--json`.
- [ ] If the package ships `_skills/<pkg>/`, `<cli> skills` exists as a
      group with `list`, `get`, and `install` subcommands. Self-contained
      (no scitex-dev runtime dep) so users can introspect bundled skills
      without discovering the ecosystem-wide tooling first. `list` and
      `get` accept `--json`; `install` defaults to symlinking
      `_skills/<pkg>/` → `~/.scitex/dev/skills/<pkg>/` and accepts
      `--claude-symlink` to also expose at `~/.claude/skills/scitex/`.
- [ ] `<cli> completion install` and `<cli> completion status` exist; `completion install` accepts `--shell {bash,zsh,fish}` and `--dry-run`. `completion install` writes a per-binary drop-in file where the shell's completion framework already looks (pattern below) and prints a one-line "open a new shell" message; it NEVER edits a shell rc file. `completion install --dry-run` prints the target drop-in path(s) without modifying the filesystem. `completion status` reports whether the drop-in exists. Legacy `install-shell-completion` / `print-shell-completion` exist only as Phase W aliases (§5 [11_deprecation.md](11_deprecation.md)).

## How `completion install` installs completion

**Required pattern: a drop-in file in the shell's own completion directory.
Never an rc-file edit.** (scitex-dev#1127)

Appending to `~/.bashrc` / `~/.zshrc` is banned, in any form (`eval` line,
`source` line, inline script). On many machines the rc file is a symlink into a
version-controlled dotfiles checkout, so an installer that appends to it dirties
a tracked file on every host that installs the package, and N CLIs append N
lines. Observed fleet-wide in 2026-11: ten `[ -f ... ] && source ...  # <prog>
tab completion` lines per host in a tracked `.bashrc`.

Write one static script per console script, generated once, to:

```
bash  ${BASH_COMPLETION_USER_DIR:-${XDG_DATA_HOME:-~/.local/share}/bash-completion}/completions/<binary>
zsh   ${XDG_DATA_HOME:-~/.local/share}/zsh/site-functions/_<binary>
fish  ${XDG_CONFIG_HOME:-~/.config}/fish/completions/<binary>.fish
```

bash-completion (>= 2, sourced by every mainstream distro's default bashrc)
loads the bash file lazily on the first `<TAB>`; fish loads its directory
automatically; zsh needs the directory on `fpath` before `compinit`, which the
installer prints as a hint and never writes.

Requirements:

- [ ] Explicit opt-in only: completion is installed by `install-shell-completion`
      (or `completion install`), never as a side effect of `pip install`, a
      post-install hook, or `scitex-dev ecosystem install` (whose
      `--with-completions` is OFF by default).
- [ ] Idempotent: an unchanged script is not rewritten; writes are atomic
      (temp file + rename, so a pre-existing symlink is replaced, not written
      through).
- [ ] Refuses to write when the target, resolved through symlinks, lies inside
      a git work tree.
- [ ] Generated with the current interpreter's Click against the registered
      group; never by executing a same-named program from `PATH`.
- [ ] Lines an older installer appended to an rc file are reported (read-only)
      so the user can delete them; the installer does not edit the rc file to
      remove them either.

The naive eval form `eval "$(_FOO_COMPLETE=bash_source foo)"` is additionally
slow (it re-invokes the CLI on every shell start, ~0.4 s per binary), and
backgrounding it (`... &`) silently breaks completion because `complete -F`
then runs in a subshell.

### Use the shared helper

`attach_shell_completion(group, prog_name=...)` (public import path:
`from scitex_dev.cli import attach_shell_completion`) implements all of the
above; every CLI that calls it inherits the contract.
A package shipping a second console script for the same group (Click keys
completion on `argv[0]`) passes it as an alias:

```python
attach_shell_completion(cli, prog_name="scitex-agent-container", aliases=("sac",))
```

The lower-level `install_completion(group, shell, prog_names, dry_run=...)`,
`completion_dropin_path(shell, prog)` and `generate_completion_script(...)` are
there for a package that mounts its own `completion install` / `completion
status` noun group. Do not keep a per-package copy of the install body.

### Audit — `PS-147 local-state-eval-completion`

- [ ] `<pkg>` source must not append shell-completion lines to a user rc file
      (`eval "$(_<PKG>_COMPLETE=...)"`, or any `open(<rc>, "a")` next to a
      `.bashrc` / `.zshrc` literal in completion code).

The auditor lives at
`scitex_dev._cli.audit._project._check_local_state.check_ps147_eval_form_completion`.
Findings surface under `scitex-dev ecosystem audit-project <pkg>` (rule code
`PS-147`, severity `W` during bake-in). The fix is to delete the local
implementation and call `attach_shell_completion` instead.

`scitex-dev ecosystem install --with-completions` (opt-in) runs every installed
package's `install-shell-completion` after a fresh pip install.
