---
description: |
  [TOPIC] Ecosystem Local State — Cross-Package Separation of Concerns
  [DETAILS] §9 — each package owns a domain and stores config other packages consume via API, never re-derived (machine-identity worked example, owner `scitex-resource`); the "when to make a new package the owner" decision (no `scitex-shared`/`scitex-common`); §9.5 the plugin-port pattern — a package must NOT hardcode or even READ another package's `~/.scitex/<other>/` tree or `SCITEX_<OTHER>_*` env var; it exposes a colon-separated env-var slot the consumer populates, keeping the dependency direction explicit; audit `PS-145`. Part of `06_dot_scitex_directory.md`. Use when one package needs a fact or extension point another package owns.
tags: [scitex-general-ecosystem-local-state-cross-package-soc]
---

# Local State — Cross-Package Separation of Concerns

Each package owns a domain; consumers call its API and never reach into
its tree. Part of the local-state layout
([06_dot_scitex_directory.md](06_dot_scitex_directory.md)).

## 9. Cross-package SoC — each package owns a domain

The `.scitex/<pkg-short>/` layout is also the canonical place each package stores config that **other packages then consume**. Rule of thumb:

> If a question has one obviously-correct answer that should be the same everywhere ("what is this machine called?", "what is the SLURM cluster?", "where is the scholar cache?"), exactly one scitex-* package owns it. Every other package imports its API.

Anti-pattern: each package re-deriving the answer (e.g. `socket.gethostname()` in five places, getting different results because of FQDN drift, login-node aliasing, container hostnames). When the answer drifts between packages, the user sees inconsistency on dashboards, in logs, in cron entries.

### Worked example — machine identity (owner: `scitex-resource`)

`scitex-resource` owns "what machine am I?" because resource detection is its domain. Config lives at `~/.scitex/resource/config.yaml`:

```yaml
machine:
  canonical_name: mba
  aliases:
    - Yusukes-MacBook-Air
    - Yusukes-MacBook-Air.local
  role: head
  hpc:                                  # optional
    cluster: spartan
    login_only: true
```

API (resolution: `$SCITEX_RESOURCE_MACHINE` → project config → user config → short hostname):

```python
from scitex_resource import get_machine_name, get_machine_config

name = get_machine_name()              # always returns the same string everywhere
cfg  = get_machine_config()            # full block with aliases / role / hpc
```

Consumers — `scitex-orochi`, `scitex-hpc`, `scitex-agent-container` — call `get_machine_name()` instead of rolling their own hostname logic. The user sets the canonical name once per host; every package agrees.

### When to make a new package the owner

Tempted to add config to `~/.scitex/<your-pkg>/config.yaml` for a fact other packages will also need? Ask:

1. **Is the fact about `<your-pkg>`'s domain?** If yes, you own it. Expose a public function. Done.
2. **Is the fact about a domain another scitex-* package already owns?** Consume their API. Don't duplicate the config.
3. **Is the fact ecosystem-wide and no package owns it yet?** Decide who *should* own it (whose name fits best), put the config there, expose the API there. **Do not** create a "scitex-shared" or "scitex-common" — that's anti-pattern (everyone depends on it, no one feels responsible for it).

The `runtime/` directory follows the same rule: `<pkg-short>/runtime/` is exclusively for *that* package's regenerable state. Never write into another package's `runtime/`.

### 9.5. Plugin-port pattern — never hardcode another package's tree

Even READS of another package's user-state directory are forbidden.
Concretely, a package X must NOT contain code like:

```python
# ❌ X knows about Y's tree.
extra = Path.home() / ".scitex" / "<other-pkg-short>" / "shared" / "agents"
if extra.is_dir():
    search_dirs.append(extra)
```

If X needs to give downstream consumers (Y) a way to extend its
behaviour, it exposes a **plugin port** — a colon-separated env var
that Y populates from Y's own tree:

```python
# ✓ X reads only from its own tree + an env-var slot.
SEARCH_DIRS = [
    Path.home() / ".scitex" / "<x-pkg-short>" / "agents",
    *[Path(p).expanduser()
      for p in os.environ.get("SCITEX_<X>_YAML_DIRS", "").split(":") if p.strip()],
]
```

Y then wires the plugin port from its own startup script:

```bash
# In Y's startup (Y's responsibility, not X's)
export SCITEX_<X>_YAML_DIRS=\
    ~/.scitex/<y-pkg-short>/agents:\
    ~/.scitex/<y-pkg-short>/runtime/extra-agents
```

Why this matters:
- X stays standalone; tests don't break when Y is uninstalled.
- Removing or renaming Y doesn't ripple into X's source tree.
- The dependency direction is explicit (Y depends on X, never the
  reverse) and documented in env vars, not hidden in path literals.

The same rule applies to **env vars**: X must not read
`SCITEX_<Y>_*` (e.g. `SCITEX_OROCHI_HOSTNAME` from a non-orochi
package). If X needs the same fact, it owns its own
`SCITEX_<X>_*` var or — better — calls the owning package's API
(see "Worked example — machine identity" above).

**Audit — `PS-145 local-state-cross-package-read`**: greps every
`*.py` under `src/` for `~/.scitex/<other-pkg>/` literals and
`SCITEX_<OTHER>_*` env-var reads (only when surrounded by
`os.environ` / `os.getenv` context — bare module constants like
`SCITEX_LOGGING_AVAILABLE = True` set by `try/except ImportError`
do not trip). Skips docstrings and `#` comments. Implementation
in `scitex_dev._cli.audit._project._check_local_state`,
severity `W` during bake-in.
