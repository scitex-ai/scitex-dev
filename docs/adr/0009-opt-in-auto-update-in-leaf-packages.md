# ADR-0009 — Opt-in auto-update belongs in the leaf package, acts only at process start, and records every transition

**Status:** Proposed (2026-08-12) — awaiting operator ruling
**Owner:** scitex-dev, as owner of the freshness/versioning surface
**Consumers today:** scitex-agent-container (host venvs + container images), every leaf package installed into `~/.env-sac`
**Related:** ADR-0006 (one store per host), ADR-0008 (declarations stay entry-point-only)

## Context

Operator statement of the problem, 2026-08-11:

> 「新しいパッケージがインストールされてないっていうのはこれずっとある問題」
> — packages not being installed after a merge is a chronic problem here.

> 「エディタブルにすると不安定になってしまう」…「automatic にアップデートされて
> ないっていうのはすごく困る」…「オートマチックアップデートをリーフパッケージ側に
> 入れるしかない」…「もちろんこれはデフォルトではオフでオプトインの機能」
> — editable installs turn unstable when a package updates, but not updating
> automatically is very painful; auto-update has to go into the leaf packages, off
> by default and opt-in.

The chronic complaint is confirmed by measurement, and the mechanism it is usually
attributed to is not the mechanism actually at work.

### The problem, measured (2026-08-11 / 08-12)

| Fact | Value |
|---|---|
| `scitex-dev` in `~/.env-sac` on scitex-compute-01/02/03/04 | **0.42.0** |
| `scitex-dev` in `/opt/venv-sac` (container, same physical hosts) | **0.47.0** |
| Latest release on PyPI | **0.47.0** |
| Releases the hosts had missed | **0.43.0, 0.43.1, 0.44.0, 0.45.0, 0.46.0, 0.47.0** — six, spanning ~7 days |
| Mechanisms that automatically upgrade a host venv | **none** — no cron line, no systemd timer, no script anywhere references `pip install -U` against `.env-sac` or `venv-sac` |
| `~/.env-sac` install integrity, before and after upgrade | `0 BROKEN` both times |

**Containers look current only because the image is rebuilt.** Host venvs have no
equivalent event, so they drift until a human runs pip. That is the whole of the
chronic problem, and it is a missing mechanism rather than a broken one.

### "Editable is unstable" is not supported as stated

The recorded incidents do not show an editable install destabilised *by a package
update*. What they show, in order of evidential weight:

1. **Editable pointers die when the checkout dies.** Twice recorded (2026-07-16;
   2026-08-09, the latter in `/opt/venv-sac` itself) an `__editable__*.pth` pointed
   into a deleted agent worktree on a deleted branch. Because a real package
   directory sat beside it in `site-packages`, **imports kept succeeding and
   `--version` kept reporting a healthy number** while the editable pointer had been
   inert for days. The aggravating factor is git worktree churn, not pip.
2. **Update-triggered breakage is real, but it is a WHEEL failure.** An in-container
   `pip install` lands as an overlayfs whiteout masking one name; swap the base image
   and the whiteout masks a name that is gone while the new base's `dist-info` is
   masked by nothing — two `dist-info`s in the merged view, entry points resolved
   against dead code by readdir order. Switching away from editable does nothing for
   this.
3. **The only genuine editable↔update interaction runs backwards.** An editable's
   `dist-info` is an install-time snapshot, so an editable checkout *always looks
   stale*; naive staleness tooling therefore hands out `pip install -U <dist>==X`,
   **which clobbers the checkout with a wheel**. `versioning/_editable.py` already
   documents this and suppresses it. The update is the damage, not the cause.

So the design must not be "avoid editable". It must be: **never act on a version
comparison alone, and re-check install integrity at the moment worktrees are
deleted.**

### A second, independent trap this investigation surfaced

Release tags are placed on the develop→main merge commits on `main`, and `main` is
never back-merged into `develop` (`auto-merge-to-develop.yaml` only merges PRs
*into* develop). `git describe` from `develop` therefore still resolves to
**v0.43.1**, and setuptools_scm versions any build from develop as
`0.43.1.devN+g<sha>` — **ordered BELOW the released 0.47.0**. An updater keyed on
"is my version lower than the latest?" would refuse a genuinely newer develop build,
or treat it as a downgrade. Version ordering is not a safe proxy for freshness in
this repository.

## Decision

**Auto-update ships as a leaf-package capability that is off by default, declared
per package in the spec, applied only in the pre-exec window at process start, and
recorded for every transition.** One design, five binding rules:

**1. Opt-in is per-package and legible from the spec.** A package/agent spec carries
an explicit block, e.g. `updates: {policy: pinned | track-release, channel: pypi}`,
defaulting to `pinned` — never auto-update. No global toggle and no hidden default:
reading a spec must tell you how that process gets its code, which is the same
property the operator wants for everything else a spec inherits.

**2. It never swaps under a running process.** The updater runs in the pre-exec
window at process start, before the interpreter imports the target package, and at
no other time. A newer version appearing while a process runs is RECORDED and
applied at the next start; the running process is left alone. This is not
conservatism — scitex-dev resolves `__version__` and many submodules lazily, so
replacing files under a live process can make an import that has not happened yet
fail against files that are already gone.

**3. It refuses to act on a version comparison alone.** Before any upgrade it must
pass the existing install-integrity guard (`sac installation check` — five reasons,
three-valued), and it must **refuse outright when the target distribution is an
editable or direct-URL install**, because such an install always looks stale and
clobbering it is the documented harm. `UNKNOWN` is not permission: unknown fails
closed.

**4. Every transition is recorded.** One row per update: package, from_version,
to_version, host, actor, timestamp, and the resolved artifact identity (wheel URL +
sha256). A package that changes under an agent with no trace makes every subsequent
bug unattributable — this entire diagnosis depended on being able to say "0.47.0
in-container, 0.42.0 on host". The ledger lives in the per-host Postgres store
(ADR-0006; sqlite is banned), and because it will be synchronised it carries
`origin_node`, `row_uuid`, `revision`, `updated_at`, `deleted_at` from creation.
Conflict resolution is per field class and never a wall clock.

**5. Freshness is decided against the RELEASE CHANNEL, not against `git describe`.**
The comparison is "what is the newest artifact on the configured channel" versus
"what artifact is installed here", resolved by artifact identity. Given the develop
tag-ordering trap above, a bare version-string comparison is explicitly not the
predicate.

## Consequences

- The chronic gap closes for opted-in packages without anyone remembering to run
  pip, and closes visibly: the ledger says what moved, when, and on which host.
- Nothing changes for packages that do not opt in — including today's entire fleet
  — so adopting this is incremental and reversible per package.
- Rule 2 means an agent can be one release behind for the length of its session.
  That is the deliberate trade: a stale-but-consistent process beats a process whose
  files changed underneath it.
- Rule 3 means an auto-updater will sometimes decline and report instead of acting.
  Declining loudly is the desired failure; the alternative is the `pip install -U`
  that destroys a developer's editable checkout.
- The develop/main back-merge gap should be fixed independently of this ADR. While
  it stands, no freshness tooling can trust version ordering, and builds from
  `develop` are mis-versioned.
- This ADR does not authorise unattended upgrades of shared host venvs as a
  migration tactic. It describes a per-process start-time capability; bulk fleet
  rolls remain a deliberate, announced operation.

## Related

- ADR-0006 — one store per host, consumed as a primitive
- ADR-0008 — job declarations stay entry-point-only
- `src/scitex_dev/versioning/_editable.py` — why an editable install must never be
  told it is stale
