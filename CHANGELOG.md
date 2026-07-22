# Changelog

All notable changes to `scitex-dev` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.37.0] - 2026-07-23

### Added
- **Release gate: a declared entry point that does not import now fails the
  BUILD (#421).** A dangling entry point does not fail the build on its own —
  the wheel uploads, `pip install` succeeds, and the breakage lands in the
  USER's tooling. `pytest11` is imported by pytest at startup, so a dangling
  target aborts EVERY pytest run in the installed environment before
  collection. `scitex_dev._release.entrypoint_imports` reads
  `entry_points.txt` from the BUILT artifact's `.dist-info` and imports each
  target in a subprocess with the artifact prepended to `PYTHONPATH`. It
  probes the artifact, not `pyproject.toml`: a correct declaration can still
  point at a module the build dropped, which is exactly the bug a source-only
  check would miss. `missing` (target absent — packaging bug) is classified
  apart from `broken` (target present, import raised — dependency/code bug);
  the two present identically at pytest startup and route to different fixes.
  Wired into `.github/ci/build-in-sif.sh`, before upload.

- **PS-222 — the `.scitex/<pkg-short>/` config-layout convention (#416).**
  New rule plus auditor covering where a package's own config tree lives,
  with a `runtime/` control arm in the test suite.

- **`ecosystem list --distributions` — enumeration keyed by origin remote
  (#419).** New `_ecosystem/_enumerate.py` resolves checkout DIRECTORIES into
  DISTRIBUTIONS by their origin remote rather than by directory name,
  collapsing duplicate checkouts and linked worktrees into reported aliases
  and labelling which tree was actually measured. `--org` cross-references a
  GitHub org listing to surface repos with no local checkout; `--scan-root`
  enumerates a directory tree, the input shape brand-wide sweeps use and
  where duplicate checkouts appear. Unreadable paths are recorded as errors,
  never silently dropped, and an orphaned linked worktree is now diagnosed by
  name instead of as a generic unreadable path. The flag is OPT-IN: the
  default `ecosystem list` output shape is unchanged, so existing callers
  keep working.

### Changed
- **PS-220 self-migration: scitex-dev's own stderr prints moved to
  scitex-logging, 132 → 118 findings (#415).** scitex-dev authored the
  no-bare-print mandate while carrying 132 findings against it. This migrates
  the STDERR bucket — 14 sites across `trace_env`, the linter
  (`_cmd_format` / `_health` / `_cmd_completion`), the argparse dispatch
  modules, `quality/_check.py` and `cron/_task_harvest.py` — where
  scitex-logging provably cannot move the output, because it already writes
  every level to `sys.stderr`. Hand-rolled ANSI in `_health` is dropped now
  that scitex-logging owns the colouring. Stdout prints are deliberately
  untouched: they need the console API still being designed.

### Fixed
- **`skills list` and `skills get` were broken and now work again (#423).**
  The symptom: running `skills list` or `skills get` raised
  `ModuleNotFoundError: No module named 'scitex_dev._core._ecosystem'` (and
  the `._docs` equivalent). This hit BOTH front-ends — argparse and Click —
  in every downstream package using the shared
  `register_skills_subcommand` / `skills_click_group` surface, because
  `_skills_click.py` imports `_skills_get` / `_skills_list` FROM
  `_skills_argparse` and so inherited the fault.

  Cause: the `dispatch.py` → `dispatch/` package split (2026-07-11,
  CLI-standardization audit pass 4b) added one nesting level. The Click
  flavors were corrected to `...`, but both argparse flavors kept the
  flat-module `..` depth, which resolves to the non-existent
  `scitex_dev._core._ecosystem` / `._docs`. 7 sites: 5 in
  `_skills_argparse`, 2 in `_docs_argparse`.

  The imports are function-local, so the modules imported cleanly and only
  exploded when a command actually RAN — which is why import-smoke and the
  split's own tests stayed green: they asserted argv PARSING and never
  called `args.func`. The new tests dispatch through `args.func` against the
  real entry points, plus `find_spec` assertions pinning that the backing
  modules live under the package root and NOT under `scitex_dev._core`.

- **`audit-project` never prints SUCC over live warning findings (#417).**
  The success banner was decided from the severity-FLOOR-filtered finding
  list, so at the default `--severity error` a tree carrying live W findings
  printed output byte-identical to a genuinely clean tree — measured on
  scitex-agent-container: 53 live PS-220 findings, `SUCC`, exit 0.

  The consequence is not cosmetic. A mutation proof driven through the CLI
  could not fail for ANY W-severity rule: planting a bare `print()` did not
  change one byte of output, so the check meant to detect it was
  structurally incapable of doing so. Every "mutation-proved" green produced
  that way was unearned. It also broke the premise PS-220's E→W restage
  (0.36.0) was granted on — that findings stay FULLY VISIBLE and only stop
  blocking.

  Reporting only; exit codes untouched:
  - `SUCC` iff zero findings at ANY severity (was: zero at the floor)
  - the clean line names the audited tree, as the failure line does
  - the headline always carries both counts: `N error(s), M warning(s)`
  - counts are taken over all surviving findings, not the floor-filtered view
  - `--json` gains `warnings` / `infos` alongside the existing `errors`
  - below-floor findings get a line naming how to list them

  `exit_code` stays `1 if n_errors > 0 else 0`. W/I still never fail CI —
  changing that would silently re-break every repo the 0.36.0 restage just
  unblocked.

- **`audit-django` never prints SUCC over live warning findings (#420).**
  The same defect, reproduced in the Django auditor and fixed the same way.
  Measured pre-fix on a fixture tree with one live DJ-107 (W) finding: the
  dirty and clean trees produced path-normalised output comparing EQUAL, and
  `--json` masked it identically (`"violations": []`, `"errors": 0` on a tree
  holding one warning).

- **`scitex_dev.audit` survives the logger-class name race (#422).**
  `scitex_logging.getLogger` IS `logging.getLogger`; the logger class is
  fixed by `setLoggerClass` state at first creation of the NAME and cached
  forever. Anything creating `scitex_dev.audit` through the stdlib first
  handed `_emit` a plain `Logger` with no `.success`, crashing every auditor
  (`_project` / `_django` / `_api` / `_summary`) — a hard `AttributeError`
  reachable purely by import ordering. The eager method table dereferenced
  `.success` on every call, so even `emit('info', ...)` crashed. The level
  method is now resolved per call via `getattr`; on a poisoned logger the
  emit goes through `Logger.log(levelno)` — scitex-logging registers level
  NUMBERS globally (SUCCESS=31 → `SUCC`), so `levelno`/`levelname` are
  unchanged, not degraded. The degrade is announced once at WARNING and
  recorded in `degraded_reason()`, so it cannot pass for a healthy run.

- **`cron list` distinguishes "crontab unreadable" from "zero installed"
  (#413).** `scitex-dev cron list` printed `installed (0): (none)` when it
  could not read the crontab AT ALL — cannot-look rendered as
  looked-and-found-zero. Reads failed soft (`read_crontab` returned `""` on a
  missing binary) while writes failed loud, and only the read path reported.
  This nearly caused a false fleet-wide automation-outage escalation: a peer
  agent ran `cron list` in a container with no `crontab` binary, read "13
  jobs registered, NONE installed", and was one step from escalating. The
  jobs were running fine on the host; only the container could not look.

  A third state (`CrontabRead` / `read_crontab_state`) is added at the source
  and plumbed through both reporting surfaces. Human output:
  `installed: UNKNOWN ('crontab' not found on PATH)` plus an explicit "this
  is NOT zero jobs installed" note; `cron status` gains a banner and per-job
  `installed: unknown` instead of a fabricated `no`. JSON: `cron list`
  reports `installed: null` — NOT `[]`, so a consumer calling `len()` cannot
  silently read zero — alongside `installed_state` and
  `installed_unavailable_reason`; `cron status` gains `crontab_state` and
  `crontab_unavailable_reason`. A non-zero `crontab -l` whose message is
  `no crontab for <user>` stays READABLE-and-empty: that is an ordinary empty
  crontab, not a failure to look. The write path is untouched —
  `write_crontab` still raises, which is correct.

- **`ecosystem test-remote` derives the xdist worker count from the CPU
  ALLOCATION, not the node (#412).** `pytest -n auto` over-subscribed an
  allocated node. The cause is narrower than "auto reads the machine's core
  count": xdist's `pytest_xdist_auto_num_workers` consults psutil FIRST and
  returns its count immediately, and psutil ignores cgroup/cpuset
  confinement; only if psutil is absent does it fall through to the correct
  `sched_getaffinity`. Measured on spartan-bm155 inside a 48-CPU lease
  cgroup: `sched_getaffinity` 48, `os.cpu_count()` 128,
  `psutil.cpu_count()` 128 — i.e. ~128 workers into a 48-CPU allocation, a
  2.7x continuous over-subscription (corroborated by worker ids reaching
  gw121 in a scitex-hub run). New `allocated_cpus()` in
  `_core/test_execution.py` resolves `SLURM_CPUS_PER_TASK`, then
  `SLURM_JOB_CPUS_PER_NODE` (including the `48(x2)` form), then
  `sched_getaffinity`, then `os.cpu_count()` — no magic cap and no hardcoded
  core count, so an unconstrained laptop still gets all its cores.
  `ecosystem test-remote` keeps `-n auto` and corrects it at its source by
  exporting `PYTEST_XDIST_AUTO_NUM_WORKERS`, which xdist consults ahead of
  psutil.

### Documentation
- **Verification doctrine added to `general/09_quality` (#414).** Every
  verification failure recorded across the fleet on 2026-07-22/23 is one
  shape: a failed measurement rendered as a confident value. The leaf states
  that once and organises the defences by claim type — absence claims need a
  positive control, causal claims need one varied variable and a hunted
  counter-example, content claims need a second independent reader, artifact
  claims need the artifact actually in use, peer claims need corroboration
  independent in kind. Carries the six-state search-failure taxonomy, the
  vacuous / inert / layer-blind / sampling control failures, the both-arms
  rule for fixing a masking bug, and the status words that fuse a failed
  measurement into a clean one (`skipped`, `declared-masked`, `0`).

- **A degrade branch is where a hard failure hides (#418).** Doctrine on
  masking: degrade paths swallow hard failures, and a mispositioned probe
  cannot fail.

## [0.36.0] - 2026-07-23

### Changed
- **PS-220 restaged: WARNING by default, error per-package opt-in.** 0.35.0
  (#406) promoted PS-220 to ERROR ecosystem-wide. The measured blast radius
  — 44 repos newly FAILING on 1856 findings, top-5 repos carrying 64 % of
  them — led the operator to restage the rollout (Telegram 1691/1692):
  「とりあえず warning で、移行できたものから red で」. The rule now
  reports at `W` for every project type, and a package opts IN to an
  error-level gate when its migration lands:

  ```yaml
  audit:
    enforce-logging:
      level: error
      reason: "print migration complete (PR #412)"
  ```

  This is staging, not retreat: every finding stays visible on every audit
  run, and nothing about what the rule DETECTS changed.

- **`audit.enforce-logging` now demands a written reason.** `error` and
  `off` deviate from the default and so carry a MANDATORY `reason`;
  `warning` is accepted bare because it IS the default and changes
  nothing. A missing or whitespace-only reason is a HARD CONFIG ERROR, not
  a silent default: the declaration does NOT take effect (the project
  falls back to `W`) AND the rejection is reported at `E`, so a package
  can never believe it is gated — or silenced — when it is not. The old
  bare shorthands `enforce-logging: error` / `enforce-logging: off` (and
  their YAML 1.1 boolean spellings `on` / `off`) are rejected for exactly
  this reason. Unrecognised values are now rejected loudly instead of
  falling back silently. Parsing lives in
  `_cli/audit/_config/_enforce_logging.py`.

  Config errors are NOT staged: a rejected exemption entry and a rejected
  enforce-logging declaration are both reported at `E` regardless of the
  project's PS-220 severity. Staging covers migration debt; a malformed
  override is not debt.

### Removed
- **The blanket `# noqa` hatch for PS-220, and its `PS-220-noqa-deprecated`
  notice.** Deprecated in 0.35.0 for one release. A sweep of all 118 repos
  under `~/proj` (8956 `src/**.py` files, 4448 flagged sites) found ZERO
  sites using it, with a planted-user control confirming the sweep could
  detect one. `audit.exemptions` — pinned to one rule at one file:line,
  with a mandatory reason — is now the only per-site opt-out.

### Fixed
- **`--version` no longer answers for another package (#409).** `scitex-ui
  --version` and `scitex-app --version` printed `scitex-dev <scitex-dev's
  version>`; 36 downstream packages reported another package's identity.
  `scitex_dev/_cli/__init__.py` fast-paths a bare `--version` to skip the
  expensive `._root` import, but the predicate matched on `sys.argv[1:]`
  alone and never checked WHO was asking. Because `scitex_dev._cli` is a
  shared primitive that downstream CLIs import (`._completion`, `._root`),
  the block fired during `import` in any process launched as `<other-cli>
  --version`: it printed scitex-dev's name and version and raised
  `SystemExit(0)` before the downstream CLI's own `main()` ran. Exit code 0,
  so nothing looked broken — and the downstream packages' own `--version`
  wiring was correct all along. The fast path now additionally requires
  `sys.argv[0]` to identify scitex-dev's own console script (or `python -m
  scitex_dev`); an unrecognised `argv[0]` declines the optimisation and
  falls through to the real Click group — correct, just slower. No path
  falls back to printing `scitex-dev`; that fallback WAS the defect.
  A library must never read `sys.argv` or exit at import time.

## [0.35.0] - 2026-07-22

### Added
- **PS-220 (no bare `print` in package source) promoted to ERROR (#406).**
  The no-bare-print mandate is now enforced, not advisory, for SciTeX
  ecosystem packages. Machine-readable stdout is spared STRUCTURALLY — a
  stdout `print` whose sole argument is a serializer call or a rendered
  payload variable does not fire, because scitex-logging writes to stderr
  and would corrupt a `--json` payload or piped data. Everything else,
  including any undecidable destination, fires and needs a per-site
  `audit.exemptions` entry carrying a MANDATORY written reason; the
  legacy blanket `# noqa` hatch is deprecated (`PS-220-noqa-deprecated`,
  `W`) and honoured for one more release. Severity is project-type
  scoped: an explicit `audit.enforce-logging` (`error` / `warning` /
  `off`) always wins, otherwise a `research` project type resolves to `W`
  rather than wedging a publish on a decision nobody has made.

  Fixes a latent hole found while implementing it: `_SEVERITY_OVERRIDES`
  was applied BEFORE the co-located rule registrations, making it a
  SILENT no-op for 31 rules — adding `"PS-220": "E"` to the override
  table did nothing at all, with no error and no warning. A severity
  table that silently ignores entries is itself a gate that cannot fail.

- **`audit.skip-rules` — sanctioned per-rule deferrals, honoured by
  `audit-all` natively.** Declaring a deferral to a named migration
  campaign in `<repo>/.scitex/dev/config.yaml` now affects BOTH gates.
  Previously the per-repo pytest wrapper honoured its `skip_rules=`
  kwarg while the org reusable workflow called `ecosystem audit-all`
  directly and bypassed it, so `develop` could be green while unified CI
  was red on identical code (measured in scitex-hub PR #433).

  Honouring is never silent. `audit-all` always emits a **MASKED
  INVENTORY** — the total, each rule id, its per-rule masked count and
  its written rationale — in the normal output, not behind a verbosity
  flag. The per-package summary now always states BOTH numbers (unmasked
  errors AND masked count) for single- and multi-package runs alike; a
  summary reporting only "0 errors" while 150 are masked is a lie of
  omission. The exit code stays driven by unmasked findings.

  **A skip entry with no written rationale is REJECTED** (exit 2, naming
  the offending entry). Distinct from the legacy `audit.skip` (bare
  codes, `audit-project`-only, silent) and from `audit.capabilities`.

### Fixed
- **The §6 MCP exemption is read from the AUDITED tree, not the runner's
  registry checkout (#405).** `_audited_repo_root` preferred the ecosystem
  registry's `local_path`, and a self-hosted CI runner's home often carries
  a `~/proj/<pkg>` checkout at exactly that path. A PR declaring
  `mcp_parity_exempt` / `mcp_tools_allowlist` in its own
  `.scitex/dev/config.yaml` therefore could never turn its own
  quality-audit green: the exemption was read from the STALE tree instead
  of the editable-installed PR checkout under audit (scitex-orochi #460;
  blocking scitex-hub #433, whose 52-entry `audit.mcp-tools-allowlist` was
  correct and declared but had no effect in CI). Resolution order is now
  import-derived root first (the tree actually being audited), with the
  registry `local_path` deciding only for non-editable site-packages
  installs where no audited tree exists on disk.
- **Every auditor summary line now NAMES its category, pass or fail.**
  The clean lines always did ("no project-structure violations"); the
  FAILURE lines did not, so `audit-all` emitted three named SUCC lines
  and then a bare `<pkg> (<path>): 3 error(s)` whose category was never
  stated. sac PRs #813 and #814 both misread a real violation as a
  broken gate because of it, wasting a CI cycle. Fixed across all five:
  `CLI conventions`, `skills`, `Python API`, `project-structure`,
  `Django-standard`.

### Changed
- `_cli/audit/_skills/_audit.py` (631 lines) split into `_registry.py` /
  `_violation.py` / `_discovery.py` / `_checks.py` + a facade, mirroring
  the sibling `_project/` package. Pure extraction; the facade
  re-exports the original public surface.

## [0.34.0] - 2026-07-21

### Added
- **CURRENCY gate — `scitex_dev.staleness.ensure_current()` (#396).** Public,
  reusable version-currency + install-integrity primitive (operator
  directive: consumers such as scitex-cards gate their invocation at ERROR
  severity). INTEGRITY half (always, local): flags ambiguous metadata
  (multiple dist-infos claiming one distribution) and partial installs
  (RECORD-listed files missing on disk — parsed from RECORD directly, since
  py3.12 `Distribution.files` silently drops missing entries). FRESHNESS
  half (fail-safe): installed vs per-dist cached PyPI latest (TTL,
  detached opportunistic refresh, never a blocking network call;
  offline → PASS), editable installs via behind-upstream git. Severity
  ladder: explicit arg > `$SCITEX_DEV_CURRENCY_SEVERITY` >
  `currency_severity` knob > `error` (raises `StalenessError` with the
  exact remedy command). `SCITEX_DEV_NO_CURRENCY_GATE=1` bypasses but logs
  a loud WARN. The scitex-dev CLI self-checks its own install integrity at
  startup (warn). Motivated by the 2026-07-21 venv incident where 0.17.4
  metadata sat over a 0.16-era file set and every version probe lied.
- **PS-221 `[all]`-closure audit rule + pyproject compliance (#395,
  consolidates #391/#393).** ERROR-severity rule: every public
  (non-underscore, non-`all`) extra must be a subset of `[all]`; scitex-dev's
  own `sync` extra brought into `[all]` (the rule's first catch was its own
  package). Plus the CLI drift-guard suppression under pytest.

### Fixed
- **Deterministic audit target-tree resolution (#397).** Explicit
  `--path` > current checkout (git toplevel of cwd, PEP-503 name match —
  correct inside linked worktrees and CI checkouts) > ecosystem-registry
  `local_path`. Previously the per-target audit CLIs injected the registry
  path as if explicit, so a CI run could silently grade a different
  develop checkout (the wrong-tree incident #395 exposed). The resolved-tree
  banner (#392) now also names which rule won (`via explicit|cwd|registry`),
  and `--json` payloads carry `resolved_via`.
- **De-flaked 6 FM001 promotion tests on figrecipe detection-skew (#394)**
  (plugin-provided rule absent ⇒ skip like their plugin-path siblings, not
  hard-fail) **and 4 xdist-order-fragile tests (#395)** (resolved-tree ×2
  pinned to the checkout under test; staleness-prefix ×2 capture
  scitex-logging via a named-logger handler instead of `redirect_stderr`).
  Two pre-existing PS-204/PS-205 violations the wrong-tree audit had masked
  were also fixed (test-file renames).

## [0.33.0] - 2026-07-21

### Added
- **`ecosystem gui` launcher + 3129X port-registry SSOT (#378, #379).** A
  fan-out launcher (`ecosystem gui list|open`) for the leaf-package browser
  GUIs, backed by a machine-readable port-registry SSOT (`RESERVED_PORTS`,
  the scitex-dev-owned 3129X/3130X assignment table) with a `gui audit`
  conformance auditor that catches port collisions and pending leaf
  migrations. Distinct from the top-level `gui` dashboard group.
- **`skills_click_group` federation primitive + PS-217 auditor (#382).** A
  shared `skills` command-group builder leaves import in one line (mirroring
  `docs_click_group`), plus a WARN conformance auditor flagging leaves that
  still hand-roll a `_cli/_skills.py` instead of the primitive.
- **CLI-normalization + packaging conformance auditors (#381, #383).** PS-216
  flags direct-URL/VCS dependencies in publishable metadata (a silent
  PyPI-upload-reject guard, even inside extras); PS-218 / PS-219 flag a
  `health` verb without `doctor` and a `version` subcommand instead of the
  `--version` flag.
- **Generalized test-execution recipe + knob + guard (#385).** A
  host/scheduler-agnostic `TestExecutionConfig` recipe (`local` |
  `remote-required`, with a `submit_template` and marker env), a per-package
  `test_execution` knob, and an auto-loaded `pytest11` guard that blocks
  local pytest when a package mandates remote — the policy layer of the
  compute-execution fabric. Fails safe (a malformed recipe never crashes
  pytest).

### Changed
- **pytest-xdist `-n auto` standardized across CI (#384).** scitex-dev's own
  pytest-matrix workflow and the `pr-ci` / `release-ci` leaf templates now
  parallelise across all runner cores (serial runs overran the ~28 min cap →
  minutes); the templates install `pytest-xdist` explicitly so `-n auto`
  works on any leaf.

### Fixed
- **PS-142 README-structure false-positive regression test (#380).** Pins the
  full-README scan so a mandatory section past the old 16 KiB truncation
  boundary is found (the underlying fix shipped earlier in #365).

## [0.32.0] - 2026-07-20

### Added
- **Per-leaf skills/mcp progressive-disclosure knobs (#372, #373, #374).**
  `PackageConfig` gains `skills_enabled` / `mcp_enabled` (default-on,
  fail-safe), a machine-managed `~/.scitex/dev/runtime/knob-state.json`
  (config.yaml is never rewritten), and a `scitex-dev skills|mcp
  {status,enable,disable}` CLI. Lets scitex-dev centrally control which
  packages' skills / MCP surface into agent context — the first piece of
  the progressive-disclosure context-budget work (measured: the skills
  corpus alone was ~30% of a 1M-token window).

### Fixed
- **timer→cron lowering must not silently drop declared guarantees (#369).**
  Lowering a `kind="timer"` JobSpec to a cron line dropped `timeout_sec`,
  `venv`, and `on_boot_sec` without a word; it now refuses (fail-loud) when
  a real guarantee would be lost, with an explicit `--allow-lossy-timer-lowering`
  opt-in and a guard-rail test that every JobSpec field is classified.
- **git-env isolation in the audit worktree tests (#371).** `_seed_repo`
  now pins `GIT_CONFIG_GLOBAL`/`SYSTEM` to `os.devnull` with an explicit
  author identity, so a broken/unreadable gitconfig on a shared runner can
  no longer flake `test_worktree_at_*`.

### Changed
- **Pruned drift-prone cruft from the skills interface corpus (#370).**
  Removed a dated generated MCP drift-report and duplicated skill-creator
  boilerplate from the surface-choice doc; the TODO backlogs were kept
  (still referenced) pending a considered cleanup.
- **Config-layout: untracked stray machine state (#375).** `.scitex/clew/db.sqlite`
  was tracked by accident; it is machine state (the `.gitignore` already
  intended to ignore it), so it is now untracked — dogfooding the config-layout
  convention (config vs. gitignored `runtime/`) before enforcing it fleet-wide.

## [0.31.1] - 2026-07-17

### Fixed
- **The audit gate graded the wrong tree (#347).** `audit_all_for_package`
  shelled `ecosystem audit-all <distribution>` with no `--path`, so
  `_resolve_repo_root` fell back to a `~/proj/<name>` guess and graded
  whatever checkout sat on the runner's disk — not the commit under test.
  Every ecosystem package's `tests/test_audit.py` calls this helper, so
  every branch's CI, including release gates, was affected. Observed live:
  on one commit the `audit` job passed (it reads the checkout) while
  `pytest-matrix` failed (it read a stale tree on the self-hosted runner),
  and three reruns of a byte-identical branch produced three different
  verdicts. A gate that grades the wrong tree is worse than no gate — it
  reports a confident verdict about source nobody asked about.
  `audit_all_for_package` now accepts a keyword-only `path` and forwards
  `--path` (`path=None` preserves prior behaviour); `_resolve_repo_root`
  prefers the CWD's git-root over the `~/proj` guess; and the audit
  surfaces which tree it resolved, so a wrong-tree run is self-evident
  rather than silent. Reported by scitex-agent-container.
- **`_package_watch` carried two concerns, leaving an orphan test that
  silently reddened develop (#348).** `test__untrustworthy_installs.py`
  had no matching source, so PS-204 failed `test_audit_all_clean` on
  develop itself and every PR inherited it. PS-204 was correct: the two
  test files already named two concerns and only the source hadn't caught
  up. `_package_watch.py` splits into `_untrustworthy_installs.py`
  (`UntrustworthyInstallWarning`, `check_untrustworthy_installs`,
  `render_untrustworthy_install_banner`) and `_package_watch.py`
  (`PackageDriftWarning`, `check_critical_package_drift`,
  `render_package_drift_banner`). Public import surface unchanged.
  Introduced by #330.
- **PS-214/PS-215 warned forever with no escalation path (#346).** A
  warning that never escalates is a finding printed under a green banner —
  the exact defect both rules exist to catch; scitex-writer's own
  `editor = []` survived repeated audit runs for precisely that reason.
  Severity is now decided per violation: absent from the `develop`
  baseline (newly introduced) → `E`, blocking; already present → stays
  `W`, reported but non-blocking, so an already-red repo is unblocked
  rather than having its backlog erased from view. Reuses the existing
  `_diff.worktree_at` baseline primitive. Reported by scitex-writer.

## [0.31.0] - 2026-07-14

### Added
- **PS-HOOK-001 — pre-commit `language: system` hooks may not invoke Python
  tools.** A bare command name under `language: system` is a `$PATH` lookup, so
  the hook runs against whichever virtualenv happens to be active at commit
  time — a different interpreter, with a different package set, on every
  machine. Measured on one repo, same config: `/home/…/.env-3.11/bin/pytest`
  on the host vs `/opt/venv-sac/bin/pytest` in the container.

  Reference incident: figrecipe's `entry: python -m pytest --testmon` +
  `language: system` hook. `pytest-testmon` was never a declared dependency, so
  the hook exited 4 (`unrecognized arguments: --testmon` / `ModuleNotFoundError:
  matplotlib`) on every machine but one. **It never ran a single test — it only
  blocked the commit**, and it had done so for weeks (zero `.testmondata` files
  existed anywhere in the fleet). The same shape cost `davinci-resolve-mcp`
  **>14 minutes on every commit**, and `pip-project-template`'s "quick smoke
  test" hook inherits `--cov-fail-under=100` from `addopts` so a smoke subset
  (~42 % coverage) can *never* pass — a permanently-red gate, replicated into
  every repo seeded from the template.

  Declaring the tool in `[project.optional-dependencies].dev` does **not** fix
  this — pre-commit never activates your dev venv. Five of the six repos found
  in the fleet sweep did declare `pytest>=8` in a dev extra; all five were still
  nondeterministic. The fix is `language: python` +
  `additional_dependencies: [...]`, which makes pre-commit build an isolated
  venv with the dep declared explicitly.

  Ships at severity **E**. The usual warn-first rollout guards against an `E`
  rule retroactively reddening consumers' CI on an unpinned `>=` floor (see the
  0.30.1 and 0.16.0 entries); that risk was *measured away* here rather than
  assumed: the rule was run against all 16 `.pre-commit-config.yaml` files in
  the fleet, where it flags exactly the 6 known-bad hooks, leaves all 9
  legitimate `language: system` hooks alone (openclaw's
  pnpm/oxlint/oxfmt/swiftlint/swiftformat + four `bash`+`grep` no-debug-code
  hooks), and flags **zero scitex-\* packages** — so no consumer's CI changes
  colour. Non-Python toolchains and explicit paths (`./scripts/tool.sh`) are
  never flagged. Opt-out: `# PS-HOOK-001: allow`.

- **Skill page `general/05_development/15_pre-commit-policy.md`** — the fleet
  policy the rule enforces: pre-commit runs fast, bounded, deterministic checks
  only (ruff, format, yaml, large-file, whitespace); the test suite belongs in
  CI, which already runs it on three Python versions per push. A gate that is
  nondeterministic across machines is worse than no gate — it blocks honest
  commits while catching nothing.

## [0.30.1] - 2026-07-13

### Fixed
- **STX-TQ001 false-positived on `@pytest.mark.skip`/`skipif` tests (#338).**
  A skip(if)-decorated test body never executes under pytest, so "no
  assertion" was not a meaningful signal for it. Because consumers
  install scitex-dev on an unpinned `>=` floor, the rule retroactively
  reddened `test_audit_all_clean` on live PRs and `develop` for at
  least one downstream consumer with zero code change on their side —
  2nd instance of this exact pattern (prior: the 0.16.0 `audit-all`
  TypeError). TQ001 now exempts `@pytest.mark.skip` / `@pytest.mark.
  skipif(...)`-decorated tests entirely.
- **`gate` printed a bare `"fail"` for an unenforced check under a PASS
  banner + exit 0 (#340).** Reported by scitex-writer: `clew-source-
  reachability` correctly evaluated as advisory (no `gate.enforce` in
  the repo's `.scitex/dev/config.yaml`), but its rendered line still
  read `fail`, contradicting the correct PASS/exit-0 result. An
  unenforced check now renders `warning (non-blocking)`; `BLOCK` is
  reserved for a check that is both failed and enforced — the only
  case that should ever flip the banner/exit code.

## [0.30.0] - 2026-07-13

### Added
- **Shared `gui` command-group lifecycle primitive + audit rule (#332).**
  `scitex_dev.gui_runtime.GuiRuntime` generalizes the state-file/pid-
  liveness/idempotent-stop pattern behind `<pkg> gui {open,serve,status,
  stop}` (doctrine `19_gui-commands.md`) so consuming packages
  (scitex-writer, figrecipe, scitex-scholar, scitex-todo) wire their own
  server bootstrap without re-implementing the same ~140 lines each.
  New audit-cli rule §12 (`_cli/audit/_summary/_gui_group.py`, WARN
  during ecosystem migration) flags legacy/flat gui-adjacent commands
  (`start-gui`, `dashboard`, `board`, a bare non-group `gui`, ...) that
  aren't a properly-deprecated Phase W/E alias, and flags a `gui` group
  missing one of the four required verbs.
- **`gui` CLI-commands doctrine: port scheme + shape refinements (#333).**
  Fixed 3129X standalone-GUI port block (figrecipe 31296, scholar 31297,
  writer 31298, todo 31299), `serve` is headless-only (no `--no-browser`,
  must expose a browsable HTTP root), `gui` is a group-only namespace
  (no positional SOURCE argument on the group itself).
- **SciTeX-wide host registry (#331).** `scitex_dev.hosts` —
  `HostRecord`/`resolve()`/`list_hosts()`, CLI `scitex-dev host
  list/show/resolve`, seeded `~/.scitex/dev/hosts.yaml` with real
  host identifiers (ywata-note-win, spartan, nas, nas1, nas2, mba)
  instead of ad hoc/vague names like "localhost".
- **Critical-package drift check in drift-report (#329).**
  `check_critical_package_drift()` compares a verified-installed
  version against PyPI-latest for a fixed critical-package list;
  responds to the 2026-07-12 incident where scitex-dev's own container
  ran stale for days with the drift timer silently not firing.

### Fixed
- **The drift detector was reading a version string that can lie (#330).**
  `check_untrustworthy_installs()` / `render_untrustworthy_install_banner()`
  surface installs where dist-info metadata and actual source disagree
  (editable-install drift, orphaned metadata, stale already-imported
  modules) — content-verified, not just version-string-trusted.

## [0.29.0] - 2026-07-11

### Added
- **Per-JobSpec venv pin (#324).** `JobSpec.venv: str | None` lets a leaf
  package pin its own venv (e.g. `~/proj/scitex-todo/.venv`) for a
  supervised service/timer, instead of the job silently resolving from
  whichever venv the `scitex-dev` supervisor itself happens to run from.
  Wired through all three execution paths: the systemd unit builder
  (`WorkingDirectory=` + `Environment=VIRTUAL_ENV=`), the `ecosystem run`
  supervisor's `subprocess.Popen` spawner (`cwd` + overlaid
  `VIRTUAL_ENV`/`PATH`), and the non-systemd shell keep-alive fallback
  (`_respawn.py`). Backward compatible — a JobSpec without `venv` set is
  unaffected. Fixes the cross-package staleness class of bug where a
  supervised service ran stale code because the supervisor's own venv
  didn't have the owning package installed (or had an older version).
- **Ecosystem boundary/ports-and-producers lint rule + ADR (#319).**
  `docs/adr/0003-ecosystem-boundary-ports-and-producers.md` codifies when a
  leaf-to-leaf import needs a port/producer indirection vs. a direct
  import; new AST-context-aware audit rule (PS-183) flags unguarded
  top-level lateral/upward leaf imports. Also promotes
  `scitex_dev.linter.spi` and `scitex_dev.cli.attach_shell_completion` to
  the public API.
- **§4b CliHelp migration, first pass (#320, #322, #323).** Continues
  converting scitex-dev's own CLI help text to the `CliHelp`/`SpecCommand`/
  `SpecGroup` dataclass spec (dogfooding the same convention scitex-dev
  enforces on other packages). `icons generate` gained a real `--dry-run`/
  `--yes` (verified: no file/dir created under `--dry-run`); 6 verb
  renames (`check-*` → `validate-*`, `set-branch-protection` →
  `update-branch-protection`, `print-path` → `show-path`), each with a
  working `deprecated_alias()` back-compat forward so existing scripts
  keep working with a warning.

### Fixed
- **`scitex-dev ecosystem audit-all scitex-dev` no longer fails CI
  (#323).** The 67 violations this surfaced were a mix of severities: 8
  were genuine errors blocking the audit gate (the CliHelp/verb work
  above); the other 59 were warn-only but printed with an `ERRO:` label
  because the auditor labels a whole batch by its worst violation, not
  per-line — those don't block CI and are tracked as documented
  follow-up (33 remain, mirroring the same "avoid rushed conversion of
  complex code" precedent already used elsewhere in this migration).
- **Latent `NameError` in `skills get`** — used `drift_warning` without
  importing it; regression test added (#323).
- **Icon generator label sizing (#321).** Label font size jumped
  discontinuously at a 3/4-character boundary (every label over 3 chars
  rendered the same size regardless of actually being 4 or 6 characters
  long) instead of scaling smoothly with label length — visible as
  mismatched icon sizes across a set of fleet Telegram-bot avatars.
  `label_font_size()` now targets a fixed on-canvas text width so size
  shrinks continuously, capped so short labels never exceed the previous
  best-case size.
- **AGPL-3.0-only license clarity, ecosystem-wide.** The FSF-provided
  "How to Apply These Terms" template text in every package's `LICENSE`
  still offered "version 3, or (at your option) any later version",
  contradicting every package's own `pyproject.toml`
  (`license = "AGPL-3.0-only"`). Corrected to "version 3 of the License
  only" across the org (only the non-operative template section touched
  — the actual license terms, sections 0-17, are unchanged).

## [0.26.0] - 2026-07-03

### Added
- **Submission-gate plugin federation + `scitex-dev gate` CLI (#285).**
  Operator-directed (cohort-A eval): a pre-submission GATE so a solver can't
  "submit" without real provenance. `scitex_dev.gate` is a new federation
  (mirroring `jobs` / `system_deps` / `linter.plugins`): packages register
  per-stage checks under the `scitex_dev.gate.checks` entry-point group; the
  `scitex-dev gate --stage=pre-submission <workdir> [--json]` CLI aggregates
  them so a hook depends ONLY on scitex-dev (SOC — each check reads its own
  state from the capsule workdir; scitex-dev stays package-agnostic).
  Contract: `GateCheck(id, stage, run, requires, description)`,
  `GateResult(passed, findings)`, `Finding(check_id, kind, message, severity,
  fix_hint)`. Severity is config-driven: a failed check is ADVISORY by default
  (warn, exit 0) and only BLOCKS (exit 2) when its id is under `gate.enforce`
  in `<root>/.scitex/dev/config.yaml` (mirrors `project-type: research`
  escalation); `gate.disable` skips a check; a crashing check fails CLOSED.
  Ships a built-in `gate-workdir-present` check so a hook can be wired and
  tested before package checks (scitex-clew `clew-source-reachability`,
  scitex-dataset `dataset-submission-format`) register. Design doc:
  `docs/submission-gate.md`.

## [0.25.0] - 2026-07-03

### Added
- **`scholar-library-sync` managed cron job (#282).** Durable cross-machine
  sync for `~/.scitex/scholar/library` (card
  scholar-library-cross-machine-sync-20260701): every 6 hours,
  `scitex-scholar library dedupe --apply` (quarantine-based, fail-loud) →
  one-way `scitex-ssh sync` push host-WSL (authority) → Spartan (never
  `--delete`; `index.db` + journal/WAL/SHM excluded as derived state) →
  remote `scitex-scholar library db build`, each stage `&&`-gated so a
  partial tree is never synced or indexed. Log under the scholar leaf's
  runtime dir. Activation (host): `pip install 'scitex-dev[sync]'` +
  `scitex-dev cron install scholar-library-sync`.
- **New `[sync]` extra**: `scitex-ssh>=1.1.0` (the `sync` CLI / `sync_dir`
  primitive) + `scitex-scholar>=1.4.3` (the `library dedupe` CLI).
- **scitex-dev's first own SystemDepSpec provider** (`_system_deps.py`):
  declares `rsync` through the same `scitex_dev.system_deps` entry-point
  federation downstream leaves use. `discover_system_deps` gains an
  `include_entry_points=False` isolation seam so unit tests stay exact
  regardless of installed providers.

### Fixed
- **Release audits no longer wedge on gitignored runner debris (#283).**
  `audit-project`'s PS-PATH-001/002 walker scanned every `config/PATH.yaml`
  on disk including GITIGNORED trees — a dotfiles-synced
  `docs/to_claude/examples` copy in a persistent self-hosted runner
  checkout failed scitex-scholar's v1.4.3 PyPI publish despite 385 green
  tests. The walker now batch-filters via `git check-ignore --stdin -z`,
  fail-open outside git (real violations are never silently skipped).
  Same runner-state-leak class as the SIF host-env item.

### Changed
- `_cli/cron/_jobs.py` hit the 512-line cap: per-job shell-line builders
  extracted verbatim to `_job_commands.py`; `_jobs` re-imports them under
  their original names (callers and tests unchanged).

## [0.24.1] - 2026-07-02

### Changed
- **STX-S010 judges verbs by a bundled lexicon, not a whitelist (#280).**
  Operator directive (via neurovista): the v0.24.0 curated verb whitelist was
  CLI-command-oriented and produced 22 false positives on real research
  scripts (`analyse`, `compose`, `register`, `translate`, …). The primary
  judge is now `_rules/_verb_lexicon.txt` — 8431 single-token English verb
  lemmas derived from WordNet 3.1 `index.verb` (shipped as package data, no
  runtime NLP dependency; includes British spellings) — plus `re`-prefixed
  derivations (`recompute`/`rerender` → `compute`/`render`) and a small
  built-in tech-verb supplement (`symlink`, `calc`, `gen`, …). The whitelist
  is demoted to the `script_verb_prefixes` extension; config semantics are
  unchanged. Missing data file degrades to defaults-only (no crash, no
  mass-flagging). Regression fixture: the 17 wrongly-flagged first-tokens,
  verified end-to-end.

## [0.24.0] - 2026-07-02

### Added
- **Supervised periodic asyncio task primitive (#275).** `runtime.PeriodicTask`
  + `PeriodicTaskGroup` run a coroutine (or, off-loop via `asyncio.to_thread`, a
  sync callable) on a fixed interval with fail-loud semantics: `CancelledError`
  is re-raised for clean shutdown (caught BEFORE the broad `except`), any other
  tick error is `logger.exception`-logged and then either continued or re-raised
  per policy — no silent stall. Supports `initial_delay` (wait before first
  tick) and an env-gate that skips ticks when the flag is unset/`0/false/no/off`.
  The shared primitive sac's six ad-hoc `while True: await asyncio.sleep()`
  loops consume, replacing per-loop error handling that silently swallowed
  exceptions.
- **STX-S009 / STX-S010 — research script-organization linter rules (#278).**
  Two research-gated (`project-type: research`), default-WARNING path/filename
  rules for a research project's `scripts/` tree. **STX-S009** flags a script
  that sits FLAT under `scripts/` (no domain subdirectory); **STX-S010** flags a
  script FILENAME that does not begin with a verb. clew hashes a script by its
  PATH, so a flat, noun-named `scripts/` churns those paths on every reorg
  (moved file → broken provenance chain); domain grouping + verb-first names
  keep the producing-session edge stable and the tree scannable. Both escalate
  to ERROR via `per_rule_severity` (existing mechanism, no new wiring); knobs:
  `script_domain_min_depth`, `script_org_exempt`, `script_verb_prefixes`.
  `load_config` now surfaces detected project types on `config.project_types`.

### Fixed
- **Figure-promotion e2e tests no longer hard-fail on figrecipe detection-skew
  (#277).** The reused Spartan CI SIF can layer a figrecipe whose checker maps a
  fixture to a different rule id than a sibling matrix leg (e.g. `STX-P002` for
  the P006 scatter pattern), so `@requires_rule` passes yet the rule never fires
  — a version-skew that hard-failed `test_p006_style_kwarg_promoted_to_error`
  and blocked the v0.23.0 release. A new `_skip_if_not_emitted` guard
  `pytest.skip`s when the rule did not emit on the fixture (reporting the ids it
  DID emit); a genuine promotion regression — rule fires but stays `warning` —
  still fails the assert.

## [0.23.0] - 2026-07-01

### Added
- **`scitex-dev service ensure <name>` — supervised long-running services (#273).**
  Resolves a `kind="service"` JobSpec from the `scitex_dev.jobs` entry-point
  federation and guarantees it is installed AND running, picking the backend at
  runtime: systemd `--user` (writes the `.service` unit, `daemon-reload`,
  `enable --now`) where a user manager exists, otherwise a respawn keep-alive
  loop (alive-flag + pidfile, capped exponential backoff, logs under
  `~/.scitex/<pkg>/runtime/logs/`). `--respawn` forces the fallback; `--json`
  emits a structured result. The durable auto-relaunch a daemon-owning leaf
  (e.g. the sac listen server) declares once and consumes — closing the
  "no supervisor" outage class.
- **Opt-in systemd watchdog for `kind="service"` JobSpecs.** A new
  `JobSpec.watchdog_sec` field emits `Type=notify` + `WatchdogSec=<N>s` ONLY
  when a leaf sets it (i.e. the daemon sends `sd_notify(WATCHDOG=1)`). Unset ⇒
  the unit stays `Type=simple` and relies on `Restart=` alone — avoiding the
  restart-storm/activation-hang footguns of emitting a watchdog for a daemon
  that never pings.

## [0.22.0] - 2026-07-01

### Added
- **`STX-NET001` — outbound network calls must pass an explicit `timeout` (#271).**
  Flags `urllib`/`requests`/`httpx`/`socket` calls on non-test code that omit a
  `timeout` (positional or keyword). Deterministic never-repeat for the
  2026-07-01 sac-listen `:7878` dead-daemon incident, where unbounded clients
  degraded to ~30s connect-hangs ("everything is slow" fleet-wide). Severity is
  `warning` under the `--new-only` gate (promotable to error after a clean
  ecosystem sweep); `# stx-allow: STX-NET001` escape hatch. Shared rule the
  leaf packages consume.
- **`ecosystem-sync` managed cron job — scheduled self-pull (#270).** Hourly
  `scitex-dev ecosystem sync --yes` (ff-only, develop-only, skips
  dirty/off-develop/diverged) fast-forwards every editable checkout so no
  install silently serves stale code. Closes the drift loop that left the
  workstation's own checkout 18 commits behind a tag. Install with
  `scitex-dev cron install ecosystem-sync`.
- **Federated cron jobs: `creds-rotate-all`, `ci-runner-ensure`,
  `ci-runner-workgc` (#269).** The operator's ad-hoc host crontab lines are
  absorbed into the managed `JOB_REGISTRY` block.

## [0.21.0] - 2026-06-30

### Added
- **Figure-lint v1 — figrecipe figure-bypass rules → research-mode ERROR (#264).**
  In `project-type: research` repos the figrecipe FM/FIG/P family (raw
  matplotlib, `tight_layout`/`constrained_layout`, `plt.subplots` bypass, …)
  is promoted from warning to error via `category_severity_override`, so the
  post-edit hook deterministically blocks figure-bypass code.
- **Raw-external-library IMPORT rules → research-mode ERROR (#265).** `STX-I001`
  (`import matplotlib.pyplot`), `STX-I002` (`import scipy.stats`), `STX-I009`
  (`import seaborn`) promote to error in research via `per_rule_severity`
  (precise per-rule, not a category bump — sibling import rules like
  `STX-I008` private-import stay warn). `# stx-allow: STX-<ID>` escape hatch
  preserved.
- **`--new-only` baseline gate for `check-files` (#266).** With
  `--new-only --baseline <ref>` (wired into `run_lint.sh` as `--baseline HEAD`)
  the edit hook blocks only NEWLY-introduced violations; pre-existing (baseline)
  findings are capped to warning so a large legacy backlog never wedges edits.
  Content-based (rule + normalized line) matching survives line shifts. This is
  the safety pair for the research-mode promotions above.
- **Worktree-resilient testmon warm-cache wrapper (`run_testmon`) (#260).**
- **`pulled` card-events emitted from `ecosystem sync` (auto-pull C8) (#257).**

### Changed
- **STX-S001/S002 messages explain WHY, not just WHAT (#263)** — the
  `@stx.session` rules now state the clew-lineage rationale.
- **PR audit gate is incremental (`--new-only`), not strict (#261)** —
  `ecosystem audit-all` in CI flags only newly-introduced violations.

### Fixed
- **Degrade present-but-broken optional deps instead of crashing (#262)** —
  `try_import_optional` broadened + numpy/torch ABI hint.
- **Pass resolved config to plugin checkers — None-config crash (#259).**

## [0.17.11] - 2026-06-11

### Added
- **`scitex_dev.jobs` federated job contract — `service`/`timer`/`cron` taxonomy.**
  Refactor of the existing `JobSpec` dataclass + the `scitex_dev.jobs`
  entry-point group into the canonical aggregator contract the
  operator commissioned. Three explicit kinds replace the prior
  overloaded `kind="systemd"`+empty-schedule footgun:
    - `kind="service"` — long-running `--user` Service. The 8051
      scitex-todo dashboard, long-poll listeners, etc. `Restart=`
      from new `restart_policy` field; `on_boot_sec` materialises as
      `ExecStartPre=/bin/sleep <N>`. Schedule MUST be empty.
    - `kind="timer"` — periodic Timer + oneshot Service.
      `on_unit_active_sec` carries the cadence; schedule is a
      fallback cron expr we derive from. Restart MUST stay `"no"`.
    - `kind="cron"` — crontab line. Schedule MUST be a 5-field cron
      expression. systemd-specific fields MUST be None.
  `JobSpec.validate()` runs at `__post_init__` and raises
  `ValueError` on every invalid combination — 13 invariants pinned
  by tests. (#153)
- **`scitex-dev ecosystem up` one-shot reconciler.** Reads every
  `scitex_dev.jobs` provider via `discover_jobs()` and installs all
  of them in one command — managed crontab block for `kind="cron"`,
  systemd `--user` units for `kind="service"`/`kind="timer"`, plus
  `systemctl daemon-reload` + `enable --now` each (with `--yes`).
  Per-unit failure is isolated and logged; the loop keeps reconciling.
  `--install-master-unit` writes
  `~/.config/systemd/user/scitex-dev-ecosystem-reconcile.service`
  (Type=oneshot, ExecStartPre=/bin/sleep 30, ExecStart=
  `scitex-dev ecosystem up --yes`, WantedBy=default.target) so the
  whole ecosystem reconciles on every boot — one master unit,
  no per-package systemctl ceremony. (#154)
- **`cred-distribute` managed cron.** Subsumes the operator's
  ad-hoc `~/.scitex/push-freshest-cred-to-spartan.sh` host crontab
  (marker `# spartan-cred-push`) into the JOB_REGISTRY. Per-host
  shell-out to `sac accounts distribute --to-host <h> --account <a>`
  every 2h, config-driven host list at
  `~/.scitex/dev/cred-distribute.yaml` (auto-bootstrapped on first
  tick). Fail-open during the proj-scitex-agent-container rollout
  window: missing `sac` binary or "no such command" stderr → SKIP +
  exit 0 (cron stays green). (#152)

### Changed
- **Drop `ecosystem daemon` CLI** — folded into `ecosystem systemd`
  since both `kind="service"` (long-running) and `kind="timer"`
  (periodic) now flow through the unified systemd installer.
  Clean break, no back-compat alias (operator no-future-debt rule).

### Migration
- Leaf packages that previously declared `kind="systemd"` should
  rename to `kind="timer"`. `kind="daemon"` → `kind="service"`. The
  new `JobSpec.__post_init__` validate() raises a clear
  `ValueError` naming the broken invariant if a stale leaf is
  installed against this release.

### Added
- **`ci-watch` cron now files CI-fails into scitex-todo (Task B).**
  When a develop CI run goes red, the existing `ci-watch` 10-min poll
  fires a fix-forward turn to the owning sac agent (existing behaviour)
  AND files a new scitex-todo entry tagged with the (repo, workflow,
  head_sha) identity — so the failure surfaces on the board, not just
  on the agent's inbox. Idempotency: a re-poll on the same failing SHA
  reuses the same task id (`ci-fail-{repo}-{workflow-slug}-{sha[:8]}`)
  and the `TaskValidationError("duplicate task id …")` thrown by
  scitex-todo's store is caught as a no-op skip — no duplicate todos.

  Wiring:
  - New `red_runs_for(repo)` returns rich `FailingRun(workflow, run_id,
    head_sha)` per failure. `red_workflows_for(repo)` stays as a
    name-only wrapper for back-compat with the existing public API.
  - New `_resolve_todo_api(store_path=None)` lazy-imports
    `scitex_todo._store.add_task` + `_store.TaskValidationError` (plus
    `_paths.resolve_tasks_path` for the default store location).
    scitex-todo is a SOFT dependency: an `ImportError` short-circuits
    to no-op + fail-open so the dispatch loop stays alive on hosts
    that don't have scitex-todo installed.
  - New `_create_todo_if_new(...)` does the actual `add_task` call;
    catches duplicate-id violations silently, re-raises any other
    `TaskValidationError`. The `todo_api` keyword is the DI seam for
    tests (PA-306 / STX-NM* — hand-rolled fakes, no `unittest.mock`).
  - `run_once` threads everything together; each `AgentResult` gains
    `todos_filed` / `todos_already_open` tuples so callers can audit
    per-pass bookkeeping. Filing happens even on dry-run + agent-busy
    paths because the todo is the *durable* record of the failure;
    the sac dispatch is the *live* nudge — either being skipped
    doesn't excuse the other.

  Mapping to scitex-todo's schema (proj-scitex-todo a2a, 2026-06-09 —
  msg `ffa6ee32`/`99d1964a`):
  - `kind="task"` (NOT `"bug"` — bug is not in `VALID_KINDS`; we prefix
    the title with `[CI-FAIL]` instead so the operator can grep).
  - `status="pending"`, `assignee=<agent>`, `project=<repo basename>`,
    `pr_url=<run URL>`, `note=` markdown block (workflow / sha / run).

  Auto-close on red→green recovery is intentionally OUT of scope for
  v1 (lead 2026-06-09 design review).

## [0.17.8] — 2026-06-09

### Fixed
- **PS-170 severity demoted from error → warning (CI emergency fix).**
  0.17.7 shipped with `audit-umbrella-pins` exiting 1 on any drift
  between the umbrella's `==` pins and PyPI's current latest. The
  umbrella's own `tests` workflow runs `scitex-dev ecosystem
  audit-umbrella-pins .` on every push / nightly cron, so every time a
  single scitex-* leaf published a newer patch wheel ahead of the
  umbrella pin bump, all matrix rows turned red — 12+ ecosystem CI
  reds flooded the operator inbox in one morning (2026-06-09 incident).

  `audit-umbrella-pins` now defaults to **warn-only**: drift is still
  surfaced (printed to stderr with a `WARN:` prefix), but exit is 0.
  The drift is informational — reproducibility belongs in the lockfile,
  the pin freshness is "nice to know" telemetry. Pass `--strict` to
  restore the old fail-on-drift behaviour for the release-pipeline
  pre-publish gate (where stale pins MUST block a tag push). The
  `audit_umbrella_pins(...)` function signature is unchanged; the new
  exit semantics live in the CLI wrapper. `_default_pypi_latest`
  resolution moved from def-time default to call-time module-global
  lookup so tests can swap the seam without `unittest.mock`.

- **`load_registry` triple-path fallback for the 0.17.0+ split.**
  The 0.11.0 layout refactor moved the ECOSYSTEM dict literal from
  flat `scitex_dev/ecosystem.py` to `_ecosystem/_core.py`; the 0.17.0
  REL-50 work then split it again — `_core.py` is now a pure re-export
  shim and the dict literal lives in `_ecosystem/_registry.py`. The
  text-scrape registry loader in `scripts/quality/audit_ecosystem.py`
  and the nightly `scitex-dev-quality-audit` GitHub Action only had
  `_core.py` / `ecosystem.py` in their candidate list, so on 0.17.0+
  checkouts they read a dict-literal-free file and silently returned
  an empty registry → the audit crashed downstream with the
  operator-visible "FileNotFoundError on ecosystem registry file"
  cascade. Both paths now try `_registry.py` → `_core.py` →
  `ecosystem.py` in order, matching the layout history.

### Added
- **`audit-all --new-only --since BASE_REF` (lead task #40 part b) —
  diff-aware audit.** New PRs were grinding on *inherited* violations
  the agent didn't introduce: scitex-todo iterated 5+ times on PRE-
  existing `TQ002`/`TQ007` debt, agent-container's develop hit the
  same. `--new-only` runs the full audit twice — at HEAD (current
  checkout) and at the base ref (default `develop`, override with
  `--since`) — and reports ONLY the net-new findings; the strict
  full audit stays the default.

  Algorithm: stage the base ref via `git worktree add --detach` into
  a tmpdir (so the caller's HEAD never moves; auto-removed via
  try/finally), spawn a child `scitex-dev ecosystem audit-all --path
  BASE_PATH` against it, parse each auditor's stdout into stable
  `ViolationKey(rule, file:line, msg_excerpt[:60])` tuples on both
  sides, and emit `HEAD-keys − BASE-keys`. First-cut identity is
  intentionally simple — a refactor that shifts every line flags
  every finding on that file as "new" (accurate-ish, since the agent
  did do the change). Refinement (line-anchor fuzzy match) lands in
  a follow-up if it bites.

  Wire-up:
  - `--new-only` + `--since BASE_REF` on `audit-all`. Same single-
    distribution constraint as `--path` (a diff-aware run is one
    repo's diff).
  - New module `scitex_dev._cli.audit._diff` (`worktree_at`,
    `compute_net_new`, `filter_to_net_new_lines`,
    `ViolationKey`, `DiffAwareSetupError`).
  - Setup failure (bad ref, dirty index, missing git) degrades to a
    warning + strict-audit fallback instead of crashing.

  Unblocks scitex-todo + clew + every future worktree agent. Pairs
  with `audit-all --path` (#137 / lead task #40a) — `--path` lets
  the agent point the audit at the worktree; `--new-only` lets the
  audit ignore debt the agent inherited.

- **`audit-all --path PATH` (lead task #40 part a) — quick fleet unblock.**
  Worktree-based agents could not self-verify the audit before pushing:
  `audit-all scitex-X` resolves the package NAME to the registry's
  `local_path` / the editable install location, ignoring whatever
  checkout the agent is actually editing. Today on scitex-todo (5+
  iterations) and agent-container's develop, every new PR has been
  grinding on inherited test-quality debt that the agent can't see
  locally — fix blind → push → CI fails → loop. `--path` lets the
  caller point the audit at an explicit checkout (their worktree)
  instead. Pass-through: each path-aware sub-auditor (`audit-project`
  / `audit-django` / `audit-python-apis`) gets `--path PATH` on its
  argv; `audit-cli` / `audit-mcp-tools` / `audit-skills` are
  intentionally NOT extended (they audit registry-resolved code) —
  added a TODO for a follow-up. The three path-aware sub-auditors
  also gain `--path` as a direct alias of the existing `--repo` flag
  so calling them by hand from a worktree works the same way.
  
  Only one distribution may be paired with `--path` (a worktree IS one
  repo); `audit-all --path /wt scitex-io scitex-stats` errors with
  exit code 2. Diff-aware audit (part b of lead task #40, opt-in
  `--new-only` / `--since develop`) lands in a follow-up PR.

- **REL-50 umbrella SSoT-drift audit + `audit-umbrella --write` + allowlist
  expansion (PR-A2).** Extends PR-A:
  - New `check_umbrella_ssot_drift` (REL-50) in
    `_release/pyproject_lint.py`: fires HIGH on every missing/extra
    `scitex[<extra>]` self-reference in the umbrella's `[all]` aggregator,
    measured against the ECOSYSTEM resolver. Auto-skips for non-umbrella
    packages; auto-degrades to LOW (skip) if the resolver fails to
    import (so the auditor never crashes on its own deps).
  - `_ecosystem/_umbrella.py`:
    - HAND_CURATED_EXTRAS gains the 4 aux-mount aliases the lead
      approved as legit (`diagram` / `media` / `torch` / `tunnel`) so
      they stop surfacing as drift.
    - New `IN_TREE_SHIM_LAZY_ATTRS` allowlist (`dev` / `fig` / `plt` /
      `session` / `social` + `canvas` / `cli` / `fts` / `schema` /
      `usage`) — suppresses the "external mismatch" / "EXTRA in umbrella"
      drift for in-tree shim lazy_attrs (external=None is correct).
  - `audit-umbrella --write` (lazy import of `tomlkit`): regenerates
    `[project.optional-dependencies].all` in the umbrella's
    pyproject.toml in place, preserving comments + whitespace.
    Hand-curated entries (`scitex[heavy]`, `scitex[dev]`, etc.) are
    merged through verbatim. New `[umbrella-regen]` extra on scitex-dev
    holds the tomlkit dep (added to `[all]`).
  - Lazy_attrs (`src/scitex/__init__.py`) and EXTERNAL_REEXPORTS
    (`src/scitex/re_export.py`) regen is intentionally out of scope:
    those need marker-based replacement to safely preserve surrounding
    code; `--check` still surfaces them and the lead applies them by
    hand alongside the `--write` output.

  Safety-gate: `--write` refuses if the umbrella git checkout has
  uncommitted edits to `pyproject.toml` or `src/scitex/` (the operator-
  edited local-SSoT rule). Other tree noise (`.scitex/clew/runtime/`,
  `.worktrees/`) is correctly ignored.

- **`scitex-dev ecosystem audit-umbrella --check` + SSoT resolver (PR-A).**
  Read-only drift detector between the ECOSYSTEM registry and the local
  `scitex-python` umbrella's `[all]` aggregator / `lazy_attrs` / 
  `EXTERNAL_REEXPORTS` surfaces. Operator 2026-06-07: ECOSYSTEM is the
  single source of truth; the umbrella is a namespace, not a re-curated
  list. Adds:
  - `PackageInfo` schema fields (`umbrella_lazy_short`, `umbrella_extra`,
    `umbrella_external`, `umbrella_core_dep`, `umbrella_skip`) — all
    optional; defaults are derived from `import_name` so most entries
    don't need to populate them.
  - `scitex_dev._ecosystem._umbrella` resolver (`expected_all_extras`,
    `expected_lazy_attrs`, `expected_external_reexports`,
    `iter_primary_mounts`, `mount_of`, `umbrella_core_deps`,
    plus `AUX_MOUNTS` for one-peer-powering-many-aliases cases and
    `HAND_CURATED_EXTRAS` for 3rd-party / dev tooling groups that stay
    hand-maintained per operator's exclude policy).
  - `ecosystem audit-umbrella` Click command — `--check` is read-only
    and lints umbrella drift; `--json` emits a machine-readable
    payload; `--write` is intentionally deferred (cross-repo write
    gate via lead/operator path, separate PR).

  Optional-peer policy (`scitex-hub` powers `cloud` / `module` /
  `project`) is preserved: those mounts ship in `AUX_MOUNTS` with
  `in_all=False` so `[all]` stays installable without `scitex-hub`.
  Audit-rule (REL-50) that fails CI on drift is reserved for the
  follow-up PR.

- **`scitex-repl` added to `ECOSYSTEM` (operator-flagged follow-on).**
  Shipped to PyPI as v0.1.1 on 2026-06-06 alongside the scitex-math
  release wave; was missing from the registry. Adds the entry to
  `_registry.py` and the `scitex_repl → scitex-repl` row to
  `ECOSYSTEM_IMPORTS_TO_DIST` in `_release/pyproject_lint.py` (REL-5
  implicit-deps scanner).

- **ECOSYSTEM registry split into `_registry.py` + new packages (#132).**
  `scitex_dev._ecosystem._core` was a 569-line file mixing the
  60-entry `ECOSYSTEM` dict with the audit-skip helpers; the data table
  now lives in `scitex_dev._ecosystem._registry` (pure data,
  intentionally > 512 lines per project line-limit exception) and
  `_core.py` keeps the helpers + re-exports `ECOSYSTEM` / `PackageInfo`
  for backwards compat. Every existing
  `from scitex_dev._ecosystem._core import ECOSYSTEM` import path is
  preserved.

  Four packages added to `ECOSYSTEM`:
  - `scitex-audit` (PyPI: scitex-audit, GH: ywatanabe1989/scitex-audit)
    — security audit orchestrator. Mounted as `scitex.audit` (umbrella
    lazy_attr + `[audit]` extra) but was missing from this registry, so
    `audit-all` and umbrella-extras reconciliation didn't know about
    it. This was the #132 blocker.
  - `scitex-core` — core infrastructure / fundamental utilities.
  - `scitex-math` — math utilities (parity helpers, etc.).
  - `scitex-linter` (`archived=True`) — kept for historical refs; the
    AST-linter rules now live in `scitex-dev` (>=0.16.0,
    `scitex_dev.linter._rules`).

  And `scitex-bridge` flagged `archived=True` (GH-archived 2026 —
  cross-module adapter shim superseded by inline integration in
  `scitex-stats` / `scitex-plt`).

  `ECOSYSTEM_IMPORTS_TO_DIST` in `_release/pyproject_lint.py` (REL-5
  scanner) gains `scitex_audit`, `scitex_core`, `scitex_math` so the
  implicit-deps lint recognises imports of those modules.

- **`worktree-gc` managed cron job** (`scitex_dev._cli.cron._worktree_gc`).
  Periodic cleanup of stale `.claude/worktrees/` directories that
  subagents leave behind when they crash, get killed, or make changes
  the operator never lands. mtime-gated (default 3 days), git-worktree-
  aware (uses `git worktree remove` + `prune`, never `rm -rf`), and
  hard-guardrailed to refuse any path that is not under
  `.claude/worktrees/` — the operator's own `.worktrees/` directory is
  never touched even if its registered path is older than the threshold.

  Schedule: `0 */6 * * *` (every 6 hours, 4 sweeps per day). Logs to
  `~/.scitex/dev/logs/cron-worktree-gc.log`. Install fleet-wide with:

  ```bash
  scitex-dev cron install worktree-gc
  ```

  Coordinates with proj-scitex-agent-container, which owns the
  RELOCATION half (stopping `.claude/worktrees/` from being created in
  the first place — the canonical path will move to `.worktrees/` at
  the repo root). Until that lands, this GC is the continuous cleanup
  loop. Motivation: the operator's host accumulated 56 stale worktrees
  before a hand-edited host cron + script were installed on 2026-06-07;
  this PR formalises that script as a managed scitex-dev job so the
  cleanup ships with the package and installs fleet-wide instead of
  living as a per-host shell script.

  Env-var overrides for ops:
  - `SCITEX_WORKTREE_GC_ROOTS` — colon-separated search roots (default
    `~`).
  - `SCITEX_WORKTREE_GC_MAX_AGE_DAYS` — mtime threshold (default 3).

### Notes
- The SSoT promotion (operator request 2026-06-07): ECOSYSTEM is to
  become the single source of truth for the umbrella's `[all]` extras /
  `lazy_attrs` map / `EXTERNAL_REEXPORTS` / MCP+CLI mounts. This PR is
  the data prerequisite; the generator + audit-rule (`scitex-dev
  ecosystem audit-umbrella`) lands in a follow-up so the umbrella-side
  changes can be staged through the lead approval gate.
- Brand-wide branch protection live on scitex-dev `develop` + `main` as of
  2026-06-03 (the policy ships in v0.17.3's `ecosystem set-branch-protection`
  command). First fleet-wide rollout pending operator confirm via lead.

## [0.17.5] — 2026-06-05

### Fixed
- **`audit-mcp` no longer crashes on namespace-pkg `__file__=None` (#116).**
  `_check_bridge_pattern` → `_read_bridge_source` did
  `Path(getattr(bridge_pkg, "__file__", "")).parent`. When the umbrella's
  `scitex._mcp_tools` resolved as a *namespace package* (no concrete
  `__init__.py`), the `__file__` attribute *existed* and was `None` —
  `getattr`'s default `""` did NOT fire (the default only kicks in when
  the attribute is missing), and `Path(None)` raised `TypeError`. This
  crashed `tests/develop/test_audit.py::test_audit_all_clean` on every
  scitex-* PR's audit step and forced an admin-merge across the
  ecosystem. Treat `__file__ is None` as "no concrete bridge file" —
  semantically equivalent to a missing bridge, which the §1 rule
  already handles silently (presence is checked under §6 parity).
  No-mock regression test (`TestReadBridgeSourceNamespacePackage`)
  pins the contract with a real `types.SimpleNamespace(__file__=None)`.

### Refactored
- **`_mcp_audit.py` split (line-cap rationale).** Same convention as
  the existing §6 split (`_mcp_parity.py`):
  - §2/§5 tool-name discipline → new `_mcp_tool_naming.py`
  - §1     bridge / mount-pattern → new `_mcp_bridge.py`
  Orchestrator drops 725 → 420 lines. Every public symbol is
  re-exported from `_mcp_audit`, so external importers and the test
  suite work unchanged.

### Docs
- **`general/01_ecosystem/11_model-serving-vs-consumption.md` (#115).**
  New ecosystem-wide rule: LLM serving (scitex-genai: multi-provider
  client + vLLM/LiteLLM recipe) is decoupled from agent-runtime
  consumption (scitex-agent-container / sac, via `ProviderSpec`
  `base_url`). Contract is an HTTP endpoint (OpenAI/Anthropic-compat),
  never a Python import — the two packages stay completely decoupled
  (neither imports the other). Only the URL+token cross the boundary
  at runtime.
- **`CLAUDE.md` persistent agent spec (#114).** Operator-facing
  persistent charter for `proj-scitex-dev` (ecosystem orchestrator
  role + cross-repo write gating).
- **Scitexification overview `SKILL.md` (#111).** Review-only SSoT
  for "the translation act" of converting external code/projects into
  the SciTeX idiom.
- **`06_dot_scitex_directory.md` §4d worked example + §4b rows (#112).**
  Concrete dotfiles-tracked `~/.scitex/` flow + `containers/` and
  `bin/` rows in the local-state layout reference.

## [0.17.4] — 2026-06-03

### Fixed
- **Release workflow `sync-main` step (closes #105).** The prior logic
  tried to fast-forward `develop` TO `main`'s SHA, which is backwards
  for the operator's actual release flow:

      git tag vX.Y.Z develop && git push origin vX.Y.Z

  develop sits AHEAD of main with every commit since the previous
  release, so `PATCH refs/heads/develop -f sha=MAIN_SHA -F force=false`
  failed with "Update is not a fast forward" (HTTP 422) on v0.16.1,
  v0.17.0, v0.17.1, v0.17.2, and v0.17.3 in a row. The failure was
  benign — `publish` + GitHub Release already succeeded — but every
  release showed a red workflow on the CI dashboard.

  New logic advances `main` → tag SHA so `main` reliably tracks "last
  released SHA": resolves the pushed tag (peels annotated tags to their
  commit), no-ops if main is already there, fast-forwards main strictly
  (force=false), and exits non-zero with a clear error if the tag isn't
  a descendant of main (rare hotfix-on-main path; human reconciles).
  Removes the obsolete "develop was auto-deleted by release-PR merge"
  branch — the operator's flow doesn't run a develop→main PR, so develop
  is never auto-deleted.

## [0.17.3] — 2026-06-03

### Fixed
- **`set-branch-protection` context-intersection regression (v0.17.2 only).**
  v0.17.2 derived required contexts from workflow filenames via a prefix
  heuristic (`pytest-matrix-on-ubuntu-py3.11` ↔ workflow `tests` etc),
  which only matched when the filename happened to share a prefix with
  the actual check-run name. On scitex-dev's first dry-run, only
  `import-smoke-on-ubuntu-py3-12` survived; the 5 other ceiling contexts
  were silently dropped. v0.17.3 swaps the heuristic for GitHub's
  `commits/<ref>/check-runs` API — the strings the protection PUT
  literally accepts. The intersection is now exact-string, not
  prefix/substring. (v0.17.2 release CI didn't surface this because the
  test seam fed shaped workflow JSON; added a new test that exercises
  the published-checks intersection directly.)

- **`unset-branch-protection` CLI verb dictionary.** v0.17.2 introduced
  the verb `unset` which isn't in the bundled Moby POS catalog. Added
  it to `.scitex/dev/cli-audit-dict.yaml` under `transitive_verbs` —
  the auditor merges that file with the user-level dict at audit time.

- **`test__branch_protection.py` PA-306 no-mocks violations.** v0.17.2
  used the `monkeypatch` fixture for injection; PA-306 flags that
  (the rule treats `monkeypatch` as a mock equivalent regardless of
  semantic intent). Replaced with direct attribute assignment +
  try/finally restoration in a fixture body — a real injection seam
  by construction. Behavioural coverage unchanged.

### Added
- New test exercising the published-check-runs intersection
  (`test_required_contexts_intersected_with_published_checks`)
  that wouldn't have caught the v0.17.2 dropout but does pin the
  v0.17.3 behaviour going forward.

## [0.17.2] — 2026-06-03

### Added
- **`ecosystem set-branch-protection` / `unset-branch-protection`
  commands.** Brand-wide GitHub branch-protection management.
  Encodes the policy from lead msg a3c59d1a:
  - 6 required CI contexts (3 pytest-matrix legs + sphinx +
    import-smoke + audit), intersected with what each repo actually
    publishes so we never demand a context the repo can't produce.
  - `strict=False` on both `develop` and `main` (don't serialise the
    parallel fleet on rebase-before-merge churn).
  - `enforce_admins=True` on `develop` (the #117 race fix —
    nobody bypasses CI on the integration branch).
  - `enforce_admins=False` on `main` (the release flow needs admin-
    merge + tag-push to fire PyPI; locking the admin out would wedge
    releases).
  - `required_pull_request_reviews` omitted (CI-green is the only gate).
  - `required_linear_history=True` (matches the squash-merge convention).
  - `allow_force_pushes` / `allow_deletions` = False.
  CLAssistant is deliberately NOT in the required set today (documented
  transient bot-timing failure mode; revisit when stable). Both commands
  default to `--dry-run`; pass `--execute` to actually PUT or DELETE.
  Sibling `unset-` is the rollback path.

  Fleet-wide rollout is gated on operator confirm via lead; first
  execution lands on scitex-dev itself for one-PR-cycle observation
  before fleet-wide PUTs.

  12 AAA + one-assert tests cover dry-run/execute semantics, per-branch
  enforce_admins, strict/linear/reviews/force-push policy bits, the
  no-develop-branch skip path (scitex-orochi shape), unknown-distribution
  exit codes, and the unset rollback path. Tests use a real
  record/replay seam on the `gh api` boundary (no `unittest.mock`).

## [0.17.1] — 2026-06-03

### Fixed
- **`audit-project` PS-108 / PS-108b slug labels (#101).** The violation tag
  that audit-all prints for these flat-package-layout rules used to read
  `[PS-108 §1 readme-missing-license-badge]` / `[PS-108b §1
  readme-missing-pypi-py-version-badge]` — slugs from long-retired README
  rules that confused every reader of the audit output. PS-108 / PS-108b
  actually detect prefix-cluster mess and too-many-flat-py-files; the slugs
  now read `src-prefix-cluster-mess` and `src-flat-py-files-over-threshold`.
  Two AAA + one-assert regression tests guard the invariant that neither
  slug contains the word `readme`. No behaviour change beyond the printed
  label.

## [0.17.0] — 2026-06-01

### Added
- **`audit-project` MVP lint rules for SciTeX/Clew conventions (`PS-PATH-001` / `PS-PATH-002` / `PS-CLEW-001` / `PS-AGENT-001`) (#98).** Four new rules under `src/scitex_dev/_cli/audit/_project/`:
  - **`PS-PATH-001` (E)** — `config/PATH.yaml` with the forbidden outer `PATH:` wrapper. The filename gives the namespace; wrapping moves real values to `CONFIG.PATH.PATH.<KEY>` and breaks 100% of access sites with `AttributeError`.
  - **`PS-PATH-002` (E)** — `config/PATH.yaml` leaf values without the `f"..."` prefix. `eval(CONFIG.PATH.<KEY>)` on bare `"./data/foo"` raises `SyntaxError` because the body parses as a Python expression `./data/foo`, not a string literal.
  - **`PS-CLEW-001` (W)** — `*.py` calls `scitex_clew.add_claim` but the same module never calls `clew.verify_claim` / `clew.list_claims` for self-verification. Encourages the "solver runs Clew at its own runtime and notices failures itself" pattern from the paper-scitex-clew operator directive 2026-06-01.
  - **`PS-AGENT-001` (E)** — `scripts/agent/*.py` registers clew claims but never persists a real `claims.json` file. The DAG terminus must be a file, not a script node.
  - 34 new tests (25 + 9 split-siblings to comply with PA-307 §3 TQ002 / TQ007).
- linter: host the scitex-umbrella `STX-I001`–`I007` (import hygiene) and `STX-S001`–`S008` (`@stx.session` structure) rules in-house as first-class engine built-ins (`_rules/_import_hygiene.py`, `_rules/_session_structure.py`, registered in `_rules.ALL_RULES`). Every id, severity, category, message, suggestion, and `requires` gate is preserved verbatim, so runtime behavior is identical — the scitex-gated rules still fire only when scitex is installed. These no longer depend on the umbrella's `scitex_dev.linter.plugins` entry-point plugin; `scitex-dev linter` surfaces them straight from its own registry. The plugin-loader mechanism is untouched (other leaf packages still use it). Umbrella-thinning Phase A — lets the umbrella delete its `scitex/_linter_plugin.py` once it pins this release.

### Fixed
- **Skill page `scientific/02_research-project_03_project-structure-config-and-data.md` (#97):** the YAML example violated the two firm rules immediately above it (outer `PATH:` wrapper + bare-string leaves). Rewritten to follow both rules unambiguously; the rules themselves are unchanged — they were already correct.

### Changed
- Untracked the orphan `docs/to_claude/examples/example-python-project-scitex/config/PATH.yaml` example (gitignored by `.gitignore:14` but accidentally tracked from before the gitignore line was added). The same file is correctly untracked in scitex-clew and scitex-io. Aligns scitex-dev with the rest of the ecosystem.

## [0.16.1] — 2026-05-31

### Added
- **`audit-python-apis` honours `.scitex/dev/config.yaml` `audit.skip`
  (PA-rule scoping).** PA-* rules can now be deferred per-project, mirroring
  the long-standing `audit-project` mechanism (`cfg.applies(rule) and rule not
  in cfg.skip`). A deferred rule is dropped from the violation set entirely, so
  it no longer drives the error-level exit code that `audit-all` gates on. This
  lets a project scope down the otherwise exception-free PA-306 (no-mocks) and
  PA-307 (test-quality) error rules — e.g. a Django app that legitimately uses
  test doubles for external services — without faking or deleting the rules.
  The `audit-python-apis` CLI command now resolves the repo root (via `--repo`
  or the registry's `local_path`, same as `audit-project`) and threads it into
  `audit_api(..., repo_root=...)`; `repo_root=None` preserves the legacy
  unscoped behaviour exactly. (The `_config` package already documented this as
  "since 0.16.1".)
- **`django` project-type relaxes PA-306 (no-mocks) to a warning.** Django apps
  legitimately use test doubles for external services (HTTP, browser, telegram,
  ssh), so the no-mocks rule is wrong-by-default for them. A `django`
  project-type downgrades PA-306 from error to warning (PA-307 still applies at
  full severity). Explicit and documented, not a silent exception. The
  `audit.skip` path remains the general, principled mechanism; the django
  default is a convenience on top of it.

## [0.15.0] — 2026-05-30

### Added
- **`audit-django` auditor — the "apps and config" Django app standard
  (ADR 0002).** New `scitex-dev ecosystem audit-django <pkg>` rule
  (also run by `audit-all`) checks a Django repo against the canonical
  layout codified in scitex-hub's `docs/adr/0002-scitex-django-app-standard.md`:
  Django project in `config/` (DJ-1xx), apps under `apps/` (DJ-2xx),
  project `templates/`+`static/` (DJ-3xx), the `src/scitex_<name>/`
  pip-package sibling (DJ-4xx), and the web stack in the `[all]` extra
  (DJ-5xx). Non-Django packages (no `manage.py`) are skipped; `scitex-hub`
  is the reference implementation and passes by definition.

### Fixed
- **`init-config --project-type` now exposes all project types.** The
  command previously offered only `Choice(["pip", "research"])` while the
  loader SSOT is `{pip, research, special, django, deferred}`, so
  `django`/`special`/`deferred` could only be set by hand-editing
  `.scitex/dev/config.yaml`. The choices are now sourced from
  `PROJECT_TYPES` (no drift) and the help documents the hybrid
  pip+django case.

## [0.14.0] — 2026-05-28

### Added
- **Dashboard GH-Release column (and MISSING signal)** — the `RELEASE`
  column on `scitex-dev ecosystem dashboard list` (default verbosity)
  now reads `MISSING` in red when a package has a local git tag but
  the GitHub Release for that tag is absent. This is the canonical
  signal for the 2026-05-27 footgun where the publish workflow's awk
  release-notes extractor failed under `bash -e`, leaving PyPI
  populated but no Release attached. The new
  `gh_release_lookup_done` flag on `PackageState` distinguishes
  "not yet queried" (dim `N/C`) from "queried, no release" (red
  `MISSING`). Markdown export gained the column too.
- **`dashboard export --format org` / `--format pdf`** — emits a
  ywatanabe-convention Org-mode report ("the usual PDF" source) and
  optionally converts to PDF via `pandoc` or `emacs --batch`. When
  neither tool is on PATH the `.org` sidecar is still written and the
  CLI prints a clear "convert on host" message (exit 0; the .org file
  is the usable artefact). `to_pdf` always writes the `.org` next to
  the requested `.pdf` output. The report includes a "GH-Release
  gaps" section listing packages with a tag but no Release.
- **`tests/results/` accepted as a known `tests/` subdir (PS-302).** Test
  runs produce a variety of artifacts beyond coverage (captured payloads,
  fixture output, relocated `.coverage` data files); `tests/results/` is
  now a first-class gitignored artifacts category alongside
  `tests/coverage/` / `tests/logs/`. Added to `_KNOWN_TEST_SUBDIRS`, the
  PS-302 rule text, and both project-structure skill leaves (general +
  scientific). Backward-compatible — nothing that passed before now fails.

### Fixed
- **GitHub Release notes extraction never fails the publish workflow** —
  the `Extract release notes from CHANGELOG.md` step in
  `.github/workflows/pypi-publish-and-github-release-on-tag.yml`
  explicitly disables `-e`, guards `CHANGELOG.md` absence, swallows
  awk errors, and guarantees a non-empty `release-notes.md` before
  exiting 0. Previously a missing `## [X.Y.Z]` section could fail
  the `release` job even after PyPI had successfully published —
  the 2026-05-27 wave bit crossref-local 0.7.4 and openalex-local
  0.7.6 (both on PyPI, no GH Release). Note: this is scitex-dev's
  own workflow only; downstream repos must re-sync the file (see
  PR for the propagation note).

## [0.13.0] — 2026-05-27

### Added
- **§6 per-package MCP-tool allowlist (`mcp_tools_allowlist`)** — packages that
  intentionally expose a *curated* MCP surface (a few high-level verbs, not a
  1:1 mirror of their Python API) can declare the exact tool names in
  `[tool.scitex_dev] mcp_tools_allowlist` (pyproject) or
  `audit.mcp-tools-allowlist` (`.scitex/dev/config.yaml`). §6 then verifies the
  registered MCP surface matches the declared set — flagging undeclared tools
  and declared-but-unregistered names — instead of the all-or-nothing
  `mcp_parity_exempt` skip or the full-API-mirror heuristic. `skills_list` /
  `skills_get` are always permitted. Helpers live in
  `scitex_dev._cli.audit._summary._mcp_parity` (`mcp_tools_allowlist` /
  `_allowlist_violations`); first adopter is scitex-ml's stateless analysis
  CLI/MCP surface.
- **§6a per-package env-var allowlist (`[tool.scitex_dev] env_allowlist`)** —
  packages that legitimately ship operator-facing env vars predating the
  SciTeX ecosystem (acronym brands like `SAC_*`, integrations with external
  operator tooling) can now declare the prefix in their own
  `pyproject.toml` instead of being forced into a global
  `SCITEX_<PKG>_*` rename that would break every running deployment.
  Entries apply "equal-to-stripped or prefix-match" — same shape as the
  universal allowlist — so `env_allowlist = ["SAC_"]` covers any
  `SAC_*` var while `env_allowlist = ["GH_TOKEN"]` covers only the
  exact name. Mirror of the existing `mcp_parity_exempt` opt-out:
  same `[tool.scitex_dev]` namespace, same checked-out-tree
  resolution (registry `local_path` when present, else walk up from
  the import location), same sparingly-used contract. Helper lives
  in the new `scitex_dev._cli.audit._summary._env_allowlist` module
  (`read_pkg_env_allowlist` / `is_var_in_pkg_allowlist`); `_audit
  ._is_allowed_env` and `_audit._scan_env_vars` consult it on every
  audit-cli run. Documented in
  `_skills/general/03_interface_02_cli/12_config-and-env.md` §6a.

## [0.12.2] — 2026-05-24

### Fixed
- **§6 MCP-parity exemption unreadable in CI** — `is_mcp_parity_exempt`
  resolved the audited package's repo root only via the ecosystem registry's
  fixed `local_path` (`get_local_path`). On CI runners that path does not
  exist (the package is editable-installed from `$GITHUB_WORKSPACE`), so a
  declared exemption (`.scitex/dev/config.yaml audit.mcp-parity-exempt: true`
  or pyproject `[tool.scitex_dev] mcp_parity_exempt`) was never read and §6
  fired for exempt packages (e.g. figrecipe's 74 matplotlib-mirror MCP tools)
  regardless of the checked-out config. `_audited_repo_root` now falls back to
  resolving the repo root from the installed tree via `importlib.util
  .find_spec` (mirroring audit-project's `_resolve_repo_root`), so the
  exemption is read from the tree actually being audited.

## [0.12.1] — 2026-05-24

### Fixed
- **audit-project orphan-hinter fd regression (#63)** — 0.12.0 switched the
  PS-204 orphan-test hinter's file discovery from stdlib `rglob` to the Rust
  `fd`/`fdfind` tool with NO fallback, so `audit-project` hard-crashed with
  `FdNotFoundError` on any runner without `fd` (e.g. GitHub `ubuntu-latest`),
  turning the quality CI red ecosystem-wide. `fd_find_files` now keeps `fd`
  as the preferred fast path but, when it is absent, emits a **loud warning**
  (`RuntimeWarning`, "fd/fdfind not found on PATH — falling back to slower
  stdlib scan; install fd for speed") and falls back to a stdlib `rglob`
  walk so the audit runs to completion. No silent fallback, no hard crash by
  default.

### Added
- **`audit.require-fd` strict knob** — a repo may opt into fail-loud-on-missing
  -fd via `.scitex/dev/config.yaml` `audit.require-fd: true` (or pyproject
  `[tool.scitex_dev] audit.require_fd = true`). When enabled and `fd` is
  absent, the orphan-hinter raises `FdNotFoundError` instead of falling back —
  for CI that wants to guarantee the fast path ran. The resolver mirrors
  `is_mcp_parity_exempt`'s pyproject + config.yaml resolution.

## [0.12.0] — 2026-05-24

### Added
- **`mcp_parity_exempt` per-package opt-out** — packages may declare
  `[tool.scitex_dev] mcp_parity_exempt` in `pyproject.toml` to opt out of
  the §6 MCP-parity audit rule, replacing transitional `skip_rules=("§6",)`
  hacks in downstream test suites (#62).
- **Research project-type (RP-2xx)** — research projects skip publish-only
  rules while keeping the universal mirror/structure rules (#58).
- **PS-173** — ADR format audit (filename convention + lean-template sections).
- **PS-149** — hard-dependency overreach (heavy lib declared as a hard dep but
  used feature-only) (#53).
- **PS-168** — per-package secret-exception config via `pyproject.toml` (#52).
- **PS-148** — downstream optional-deps guarded in `src/` (severity W during
  ecosystem adoption) (#51).
- **quota-keepalive** managed cron job (#50).

### Changed
- **Ecosystem registry: `scitex-cloud` → `scitex-hub`** — renamed the cloud
  package identity in the ecosystem registry (#61).
- **audit-all** — parallelized per-audit dispatch with `fd`-backed file
  discovery for faster ecosystem audits (#49).
- **MCP tool listing** — routed through `get_tools_sync` for FastMCP 2.x/3.x
  compatibility (#47).
- **Sphinx** — fixed 11 warnings and enforced `-W` (warnings-as-errors) on the
  develop docs gate (#48).

### Fixed
- CI `_sphinx_html` commit-back step made non-fatal.
- Codecov PR comments disabled to stop email noise.

## [0.11.17] — 2026-05-16

### Added
- **Branding registry + PS-2xx audit** — single source of truth for
  package branding, with PS-2xx rules auditing README / pyproject /
  docs against the registry. Ships the new `scitex_dev._branding`
  module (`get`, `get_env`, `register_method_aliases`) that figrecipe,
  socialia, and other ecosystem packages consume.
- **Ecosystem CLI** — `--help` now organizes subcommands by category;
  added `bulk` fan-out for running a command across all packages;
  `list --category <name>` filters packages by category.

### Changed
- Audit refinements:
  - **PS-167** — refined detection logic to reduce false positives.
  - **PS-201** — shim tolerance: allow thin re-export shims to satisfy
    the rule without tripping the audit.
  - **PS-202 / PS-204** — test path convention now mirrors source path.
- Test infrastructure: split `test.yml` into a pytest matrix and an
  import-smoke job; renamed workflow files for clarity.

## [0.11.16] — 2026-05-15

### Added (audit rules)
- **PS-164** — workflow-naming convention (one-file-per-check; descriptive
  filenames; short top-level `name:` labels).
- **PS-211** / **PS-212** — `tests/smoke/` and `tests/e2e/` directory rules.

### Changed
- **PS-122** — RTD detection is now content-based (looks for a `sphinx-build`
  step) rather than filename-based, so the rule survives workflow renames.
- Workflow files renamed to the PS-164 convention:
  - `docs.yml` -> `rtd-sphinx-build-on-ubuntu-latest.yml`
  - `newb.yml` -> `newb-docs-quality-on-ubuntu-latest.yml`
  - `publish-pypi.yml` -> `pypi-publish-and-github-release-on-tag.yml`
  - `quality-audit.yml` -> `scitex-dev-quality-audit-on-ubuntu-latest.yml`
  - `sync-main.yml` -> `sync-main-to-release-tag-on-push.yml`
  - `test.yml` -> split into `pytest-matrix-on-ubuntu-py3-11-3-12-3-13.yml`
    and `import-smoke-on-ubuntu-py3-12.yml`.
- README badges normalized to `shields.io` short labels
  (`docs`, `tests`, `install-check`, `quality`, `cov`).

### Fixed
- `audit/_project` — resolve `_spdx_from_pyproject` undefined reference.
- `audit/license` — `tomli` fallback for Python 3.10 (`tomllib` is 3.11+).
- `audit` — `skip_rules` now matches `ERRO:`-prefixed lines and reads stderr.

## [0.11.5] — 2026-05-07

### Fixed
- **PS-502 / PS-503 ignore `.ipynb`-only stems.** When an example's
  stem is owned by a `.ipynb` file (no matching `<n>.py`), the
  rendered cell outputs ARE the demo — the `_out/` sibling is
  optional and any legacy directory left over from a `.py → .ipynb`
  migration does not trigger PS-502/PS-503. Rules still fire when a
  `.py` example is present.

## [0.11.4] — 2026-05-07

### Added (audit rules — README structure)
- **PS-141** (audit-project) — README.md must have a mandatory `## Demo`
  section whose body contains at least one visual element (markdown
  image, non-shield HTML `<img>`, or fenced ```mermaid block).
- **PS-142** (audit-project) — README.md must have a mandatory
  `## Architecture` section. Accepted body forms: ```mermaid fence,
  ASCII text diagram (fenced ≥10 lines), file-tree characters
  (`├──`/`└──`/`│`), or `<img>` tag.
- **PS-143** (audit-project) — README.md sections must appear in the
  canonical order: `Problem and Solution → Installation →
  Architecture → <N> Interfaces → Demo → Quick Start → Part of
  SciTeX`. Optional sections may be skipped; relative order of those
  present must hold.
- **PS-144** (audit-project) — `## Problem and Solution` table cells
  must (a) contain ≥1 `**bold**` span, (b) keep bold coverage ≤30%
  of cell text, and (c) stay ≤200 characters per cell. Bolding entire
  sentences defeats emphasis; flat prose defeats the table.

### Added (audit rules — examples chapter)
- **PS-503** (audit-project) — `examples/<n>_*_out/` must contain a
  `FINISHED_SUCCESS/<session_id>/` subdirectory with at least one
  tracked artefact. Proves the example was run end-to-end via
  `@stx.session`, not hand-fabricated.
- **PS-504** (audit-project) — `.ipynb` example must commit cell
  outputs. GitHub renders cell outputs inline; a stripped notebook is
  invisible to viewers. Detected by walking the notebook JSON for any
  `code` cell with a non-empty `outputs` list.
- **PS-505** (audit-project) — `tests/examples/test_<n>.py` for an
  `.ipynb` example must invoke `jupyter nbconvert --execute` or
  `pytest --nbval[-lax]`. Subprocess `python <name>.ipynb` does not
  execute notebook cells.
- **PS-506** (audit-project) — `.ipynb` that imports `matplotlib` must
  include the `%matplotlib inline` cell magic. Without it the figure
  outputs aren't embedded in cell outputs and rendered notebooks on
  GitHub show no plots.
- **PS-507** (audit-project) — `.ipynb` that imports `matplotlib` must
  call `plt.show()` at least once. Even with `%matplotlib inline`,
  deferring display can leave figures un-rendered.
- **PS-508** (audit-project) — `.ipynb` example must not contain
  warning output (DeprecationWarning, UserWarning, FutureWarning, etc.)
  in committed cell outputs. Demos must run cleanly. Detected by
  scanning cell `outputs` for stderr-stream warnings or
  `output_type=error` with a `Warning`-named class.

All six new rules default to severity `error` (CI-failing). The
notebook-aware checks live in `_check_examples.py` and parse the
notebook JSON locally — no execution, fast.

## [0.11.3] — 2026-05-07

### Added
- `audit_all_for_package(..., skip_rules=("PS-108b", "PS-121"))` —
  packages can locally bypass aspirational structural rules from their
  `tests/develop/test_audit.py` while a refactor is pending. The
  ecosystem default keeps these rules at `error`; opt-in only.

### Fixed
- **Top-level compatibility shims now ship in the wheel:**
  `scitex_dev.decorators`, `scitex_dev._skills_quality`, and
  `scitex_dev._skills_quality_pytest`. Consumer packages
  (`scitex-dataset`, etc.) import these top-level paths; the actual
  implementations moved to `scitex_dev._ecosystem._skills.*` but the
  shims preserve the public import surface. v0.11.2 was missing them,
  so every consumer's CI failed with
  `ModuleNotFoundError: scitex_dev.decorators` /
  `scitex_dev._skills_quality_pytest`.

## [0.11.2] — 2026-05-07

### Fixed
- **`scitex_dev/testing/` subpackage now ships in the wheel.** It was
  added after the v0.11.1 tag, so the published v0.11.1 wheel was
  missing it — every package's `tests/develop/test_audit.py` failed in
  CI with `ModuleNotFoundError: No module named 'scitex_dev.testing'`.
  v0.11.2 unblocks the test-suite-integrated audit gate across the
  ecosystem.

### Added (audit rules)
- **PA-304** (audit-python-apis) — standalone source must not import the
  umbrella (`from scitex.X` / `import scitex` / `import scitex.X`).
  Module-level only; function-scoped lazy imports + `__main__` guards
  exempt; `examples/`, `docs/`, `_demo_*.py` files exempt;
  umbrella-private (`scitex._foo`) exempt.
- **PA-305** (audit-python-apis) — modules importing `playwright.async_api`
  must call `scitex_browser.debugging.capture_debug_artifacts_async`
  somewhere in the same module.
- **PS-139** (audit-project) — standalone `pyproject.toml` must not list
  `scitex` (umbrella) as a runtime or extras dependency.
- **PS-140** (audit-project) — packages with cross-package imports must
  ship `tests/integration/test_cross_package_imports.py`. Stale
  `CROSS_PACKAGE_IMPORTS` lists also flag.
- **§1a** — `install-shell-completion` and `print-shell-completion`
  subcommands are now mandatory for every CLI (was advisory).
- **§2 no-interactive-prompts** — CLI source must not call
  `click.confirm`, `click.prompt`, `getpass.getpass`, or bare
  `input()`. Mutating actions gate on `--yes`/`-y` instead.

### Added (helpers + skills)
- `scitex_browser.debugging.capture_debug_artifacts_async` — async
  helper that saves screenshot + HTML in one call. Used by
  `click_with_fallbacks_async` / `fill_with_fallbacks_async` to
  auto-capture before/after every interaction by default (opt-out via
  `capture_debug=False`).
- `_skills/general/02_package_09_browser-automation-debugging.md` —
  rule + pattern + anti-patterns for stepwise PNG+HTML capture.
- `scitex-dev ecosystem write-ci-workflow <pkg>` — materialises the canonical
  `.github/workflows/audit.yml` inside a package's local checkout. The
  generated workflow runs `audit-all` on every push and PR, with no
  `continue-on-error`; failure is driven by the audit-all exit code.
- `scitex_dev._ecosystem._core.should_skip_audit(pkg, auditor)` — single
  source of truth for "does this auditor apply to this package?". Each
  auditor consults it on entry and emits `skip pkg: <reason>` when the
  package's category doesn't apply.

### Changed
- **Audit rule severities promoted `warn` → `error`.** Per the 2026-05-06
  directive, every actionable rule with a documented spec now defaults to
  `error` severity (CI must fail). 38 project rules + 11 CLI/MCP § sections
  promoted in one sweep. Rules can be demoted back to `warn` only after a
  documented false positive lands on develop.
- **Audit exit codes now reflect actual severity.** `run_audit`,
  `run_audit_mcp`, and the `*_all` variants now return `1` whenever any
  violation reaches `error` severity (warnings alone exit `0`,
  not-auditable exits `2`). Previously every audit returned `0` regardless
  of violations, hiding ecosystem-wide drift from CI.
- `_emit_human` now labels lines `error pkg: N error(s)` vs
  `warn pkg: N warning(s)` based on the highest severity present, instead
  of always saying "warn".
- `_skills/general/02_package_07_github-actions.md` corrected the CI
  failure-policy section: `continue-on-error: true` is forbidden (it
  hides the signal); merge-gating uses branch-protection required-checks
  instead.

## [0.11.1] - 2026-05-06

### Added
- `attach_shell_completion(group, *, prog_name)` helper for any click
  group to register `install-shell-completion` and
  `print-shell-completion` subcommands consistently.

### Fixed
- `<cli>` placeholder substitution in shell-completion help text.
