# Changelog

All notable changes to `scitex-dev` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.59.0] - 2026-09-02

> `0.58.1` was tagged on `develop` rather than on `main`, so `v0.58.1` was
> reachable only from `develop` while `main`'s newest tag stayed at `v0.58.0`
> and `main` sat 48 files behind — even though PyPI was already serving
> 0.58.1. That is the same shape the 0.58.1 note below describes, recurring
> one hop later. This release is cut from `main` AFTER promoting `develop`
> into it, so the tag, the branch and PyPI describe the same tree.
>
> The identical drift was found and closed in `scitex-template` the same day
> (PyPI 0.7.0 against a `v0.6.8` tag on main), which makes it a fleet-wide
> pattern rather than one repo's accident.

### Added

- **`scitex_dev.store._policy`** — a declared policy for how a field may be
  merged, so that a value computed across the whole table can say it has no
  meaningful merge instead of being silently last-write-wins. Pure in-memory:
  no database import, no connection.
- **`scitex-dev ecosystem --repair-tail`** (PS-140) — the rule named a fix and
  the one command a reader would actually run did nothing about it. The repair
  is now performed rather than described.

### Fixed

- **The audit's own tally line was read as a violation.** A line reporting
  `ERROR: 3 violations` matched the violation pattern, so the report counted
  itself.

### Documentation

- **ADR-0013** — Postgres 55432 identity, per-principal roles and DB-enforced
  authorship, with the two measurements that change what can be claimed: the
  cross-host reconciler is a principal the role model cannot express, and
  `application_name` is unset on every connection, so the incarnation axis has
  zero adoption rather than partial.
- **ADR-0006** — the ruling that forbids today's topology was still marked
  Accepted.

## [0.58.1] - 2026-08-31

> `v0.58.0` was tagged on `main` on 2026-08-30 but never published: its test
> leg failed on the shared PostgreSQL primary's connection ceiling (fixed
> below), so `build`/`publish`/`release` skipped on `needs: test` and no
> wheel, no GitHub Release, and no PyPI upload exist for it — `pypi.org`
> still serves `0.57.0`. This release carries everything that would have
> shipped as `0.58.0` plus two more fixes that landed on `develop`
> afterward, tagged directly on `develop` rather than on a `main` merge
> commit that does not yet contain them.

### Added

- **`scitex-dev ecosystem branch-hygiene`** — the daily two-dimensional branch
  sweep, over every package in the ECOSYSTEM registry on every host in the host
  registry. Three legs: put each checkout back on `develop` (a dirty tree is
  reported and skipped, never stashed and never forced); collect local branches
  that are not `main` / `master` / `develop` / `cla` / `cla-signatures` by EXACT
  name (BOTH CLA spellings — they are both live signature stores in this org,
  carrying the identical `signatures/cla.json`),
  are not an open PR's head, and either merged into develop or went untouched
  for 24h; and the same rule against `origin`, run ONCE for the fleet. A
  worktree holding a finished branch goes with it — cleanly when the tree is
  clean, with `--force` only when it carries uncommitted work whose FILES are
  also past the window, and every such discard is named. DRY RUN BY DEFAULT;
  `--execute` opts in. Decisions live in the new `scitex_dev.branch_hygiene`
  package.
- **`scitex-dev-branch-hygiene` and `scitex-dev-branch-hygiene-remote`** — the
  two daily JobSpecs behind it, running on the supervisor's clock per ADR-0012.
  The local leg arms everywhere (every host has its own checkouts); the remote
  leg is placed on the control-plane host, because remote refs are shared. Both
  ship in REPORT mode, like `pr-expire`.
- **`scitex-dev dev hooks enable-pre-commit`** — installs the guard that refuses
  a commit whose HEAD is `main` or `master`, AND wires `core.hooksPath` so it
  actually fires. Local `main` is a read-only mirror of `origin/main`; the
  refusal NAMES THE ROAD (develop → topic branch → PR → release → pull) rather
  than only saying no. The release path tags and pushes and never commits, so
  it is untouched.
- **A guard detector now declares itself** with a `abolition-guard: detector`
  marker instead of the abolition guard exempting its own scanner file by
  comparing the scanned path against `__file__` — a privilege no detector in
  another repository could claim. Needed so a downstream package (scitex-io,
  rule `IO015`, forbidding `sqlite3.connect()`) can register its own
  self-scan exemption the same way, rather than the guard special-casing
  every caller by name (#772).

### Changed

- `core.hooksPath` wiring moved into a shared `_hookspath` helper used by both
  `enable-pre-push` and `enable-pre-commit`, so the two cannot drift apart about
  what "already set" means. Behaviour is unchanged: additive, then refuse.
- **The test suite no longer runs against the shared production PostgreSQL
  primary.** A `v0.58.0` release-pipeline run and every agent's card write
  were competing for the same 100-connection ceiling; the release leg failed
  with `remaining connection slots are reserved for roles with the SUPERUSER
  attribute`. CI now starts an ephemeral `initdb`/`pg_ctl` cluster per test
  leg (the `ci-cpu` image now ships a PostgreSQL server), so a test run can
  no longer deny service to the production board (#781, #782).
- The extras surface is documented as exactly `all` — the only permitted
  extra name — and the leaves that still described a per-feature menu are
  reconciled to match (#784).
- CI pin maintenance: the CLA reusable workflow pin was bumped past the
  signature-branch rename (#779) and again off the self-hosted runner
  (#773); the SQLite-out guard test and the abolished `newb` workflow were
  removed from CI, both already gone from what they were checking.

### Fixed

- **`audit-mcp-tools §1` no longer fails one package's required check for
  another package's defect.** The rule grades
  `scitex/_mcp_tools/<pkg>.py` — a file that ships in the UMBRELLA — and
  reported the verdict against whichever package was under audit, at
  error tier. In scitex-io's CI that read `[§1] scitex-io: umbrella bridge
  scitex/_mcp_tools/io.py uses direct mcp.mount(...)`, a file scitex-io
  does not contain, does not depend on (the umbrella arrives
  transitively) and cannot pin.

  The control: scitex-io PR #167 resolved no `scitex==` at all and showed
  NO §1, from the same repository and the same rule. The finding appeared
  or vanished purely on whether the umbrella happened to be installed in
  that job — a fact about the environment, not about the package graded.

  Such a finding is now emitted as **`§1u`**, attributed to `scitex` (the
  printed line names the owner) and registered **warn**-tier, so it stays
  fully visible and counted without failing a gate its subject cannot
  pass. The message says which repository to fix it in and why the
  audited package cannot. `§1` keeps its error tier for the owner's own
  run. Warn-tier sibling of an error rule, same construction as `§10w`
  beside `§10`; `§1u` also joins `NON_ATTRIBUTABLE_RULES`, since a
  finding that flips with the resolved umbrella cannot be blamed on a
  diff either.

  Known gap, stated rather than implied: §1 is warn-only in practice
  today, because `audit-mcp-tools` skips the umbrella outright and would
  otherwise look for a `scitex/_mcp_tools/scitex.py` that does not exist.
  Making §1 bite its owner needs the umbrella's audit to sweep its own
  bridge directory — a separate change, recorded in `_mcp_bridge`'s
  docstring.

- **A tally line counting errors was itself read as an error, defeating
  `skip_rules` for every ERROR-tier rule fleet-wide.** The conformance
  harness classifies a run's output lines by tier and collects the
  error-tier ones as violations. A summary line like `ERROR: 3 violations`
  is a TALLY — it reports how many errors were found, it is not one itself
  — but it named no rule, so no `skip_rules` entry could ever match it, and
  a report whose individual findings were all skipped still failed the
  gate on its own count line. Fixed with an explicit tally discriminator
  (`_TALLY_COUNT_RE` / `_is_tally_line`) applied where the tier
  classification already runs. Reported by scitex-hub, who hit it on their
  own report (#744).
- The conftest walk descended into `.git`, which the audit itself mutates
  mid-run (`git worktree add`/`remove`/`prune`); a transient
  `FileNotFoundError` on a pruned `.git/worktrees` could kill a release
  test leg on one runner while the same commit passed on another.
  `_conftests_under()` now prunes dot-directories in place during
  `os.walk`, instead of filtering results after the descent already paid
  for them (#744).
- **`sac --version` (and any editable-install currency check) no longer
  reports a healthy `develop` checkout as STALE forever.** Release tags
  live on `main`, so a healthy `develop` is permanently "behind" the
  latest tag — that fact alone used to trigger a `git pull --rebase`
  remedy that could never close the gap, because a pull only moves HEAD
  toward its tracking remote. The probe now separates "distance from the
  latest tag" (annotation only) from "distance from the tracking remote"
  (the only gap a pull can close) and raises STALE on the second only; the
  surviving remedy is `git -C <repo> pull --ff-only`, never `--rebase`
  (#785).
- **The zero-config default host store resolved to a read-only replica,
  silently.** `host_store()` built a UNIX-socket DSN for whichever host's
  local PostgreSQL was reachable; measured live, every host's local
  `55432` reports `pg_is_in_recovery()=TRUE` and shares one
  `system_identifier` with `scitex-primary` (100.64.0.5, nas-03), which is
  `FALSE` — one cluster, streaming replication, and only the primary is
  writable. Resolving to a replica failed nothing at resolve time or
  connect time; the first symptom was a write refused far away, or reads
  that were merely stale forever. The default now resolves to the central
  primary; the test harness also stops reaching the fleet board (#774).
- **An ignore rule that names the retired storage engine in order to
  refuse it is no longer flagged by the abolition guard as a mention of
  it.** `**/*.sqlite` in a `.gitignore` is a standing refusal to accept
  those files, not a reference to the engine — but the guard's one
  exemption (the guard's own scanner file) did not cover it, so a repo
  adopting the guard had to choose between keeping the ignore rule and
  passing the scan. Measured cost of getting this backwards: scitex-ssh
  had 55 committed database files land uncaught because no ignore rule
  covered them, and being binary they were invisible to `git grep -I` too
  (#771).

## [0.57.0] - 2026-08-30

> **BREAKING: there is one storage engine.** The second, file-backed
> backend is gone — its `Backend` member, its `StoreTarget` constructor and
> its dialect are removed, not deprecated. `Backend` now has one member. A
> store resolves to PostgreSQL or refuses.
>
> (The retired engine is not named here, and the guard under
> `tests/develop/` that enforces that will reject this file if it is. The
> name is allowed only under `docs/adr/`, which is where the record lives:
> **ADR-0006**.)

### Removed

- **The file-backed backend: its `Backend` member, `StoreTarget`
  constructor and dialect** (#762). The reason is not tidiness. A database
  in a file has no concept of WHO — anyone who can open it holds every
  permission — so multi-user identity cannot be retrofitted onto it: it is
  a foundation or it is absent, and handing a collaborator a database file
  is SHARING, not COLLABORATING.

  Keeping it reachable kept it CHOSEN. A fleet survey counted 66 of 68 live
  tables in one consumer package sitting on it, put there by readers
  following a default that existed only in prose. A default stated in prose
  is still a default; the fix was to stop shipping the thing it pointed at.

  There is no shim. A caller that constructed such a target moves to
  PostgreSQL — a silent private store is the exact failure this removes.

### Added

- **`scitex_dev.store.testing`** (#762) — `writable_dsn()`,
  `ephemeral_schema()`, `ephemeral_cluster_dsn()`. Removing the second
  engine removed the affordance consumers used to test store-touching code
  (a throwaway file-backed store), and nothing replaced it; three packages
  hit that wall on the same day. This hands out a REAL PostgreSQL — a
  throwaway schema on a cluster you already have, or a whole throwaway
  cluster started with `initdb` — so a test that passes against it passes
  against the engine that ships. It checks `pg_is_in_recovery()` rather
  than assuming: a standby accepts the connection and refuses the DDL,
  which is the shape that makes a suite report green while running nothing.

### Fixed

- The release pipeline had no writable PostgreSQL, so no tag could publish
  (#765).

> **The store could be read by key or in full, and by nothing in between** —
> so a package with a filter had to fetch the table and narrow it in Python,
> which is the point at which it stops using the store and starts building
> an index of its own.

### Added

- `Store.search(Query)`, `Store.count(Query)` and `Store.tally(field, Query)`
  — the middle of the read door. A `Query` is an immutable description built
  from `eq` / `ne` / `gt` / `gte` / `lt` / `lte` / `is_in` / `contains` /
  `nonempty` / `is_null` / `either`, plus `matching` (full text),
  `ordered_by`, `limited` and `with_hidden`.

  It names FIELDS, never SQL. Every field is checked against the schema
  before a statement is built, so a typo raises instead of returning an
  empty set, and nothing a caller types reaches an identifier position.
  Values travel as bind parameters.

  Two engine behaviours are pinned rather than inherited: `NULLS LAST` in
  BOTH directions (Postgres defaults to NULLS FIRST under `DESC`, which
  would lead "most downloaded" with every row whose count was never
  recorded), and a record-key tie-break appended to every `ORDER BY`, so
  `LIMIT`/`OFFSET` paging cannot show one row twice and skip another.

- `Schema.build(..., text_search=(...), text_config="english")` — full-text
  search, declared once per schema. The GIN expression index the store
  creates and the match expression the query builds are generated from that
  single list, because an expression index that differs from its query by
  one character is silently never used, the planner reports nothing, and the
  only symptom is that search got slow. Matching uses
  `websearch_to_tsquery`, which never raises on malformed input — the text
  came from a person, and `to_tsquery` would turn a half-typed search box
  into a syntax error.

  `contains()` is real JSON containment (`@>`), not a substring match on the
  serialised column, so asking whether a modality LIST holds `eeg` is no
  longer also answered by a description that mentions it.

### Changed

- The read door moved out of `_store.py` into `_read_door.ReadDoor`, a mixin
  of `Store` alongside `PeerState` and `IdentityState`. No method changed
  name or behaviour. Reading and writing change for different reasons, and
  `_store.py` had already outgrown the repository's file-size limit.

## [0.56.8] - 2026-08-28

> **The probe added in 0.56.7 answered about every schema, not this one** — so
> it could skip creating tables that were not there.

### Fixed

- `PostgresDialect.columns_sql` and `PostgresDialect.indexes_sql` are now
  scoped to `current_schema()`. They filtered on `table_name` / `tablename`
  alone, and both catalogues span EVERY schema the role can see. With a
  store's tables present in one schema and the connection pointed at another,
  `PeerState._schema_objects_missing` answered PRESENT, `create_sql` was
  skipped, and the first read failed against tables that were never created
  here:

      psycopg.errors.UndefinedTable:
          relation "comms_blocks_rows" does not exist

  `current_schema()` is the right scope because it is where an unqualified
  `CREATE TABLE` lands — so the probe and the creator now mean the same
  schema. Measured on one tree against one writable primary, changing only
  the dialect: without the fix the read raised `UndefinedTable`, with it the
  store opens and the full store suite is 334 passed, 1 skipped.

### Notes

This corrects a claim 0.56.7 made about itself. Its release note said the
probe "can only remove DDL that would have changed nothing", and
`columns_sql`'s docstring named the cross-schema exposure and shipped anyway
as "the same exposure in principle". It was not hypothetical — it turned every
open PR in `scitex-agent-container` red the moment those tests ran against a
real cluster.

The probe's own tests never ran on Postgres, which is why a Postgres-only defect
got through. The two tests added here assert on the STATEMENT, so they run
everywhere rather than only where a cluster happens to be up; a third
reproduces the end-to-end shape and skips when no cluster can host a
throwaway schema.

## [0.56.7] - 2026-08-28

> **Opening a store demanded the right to CREATE it** — so a role with full
> read/write on every table of a store could not open that store at all.

### Fixed

- `Store.__init__` now runs `create_sql` only when something it would build is
  actually absent. Every statement carried `IF NOT EXISTS`, so re-running it on
  an existing store looked free; on PostgreSQL ownership is checked BEFORE that
  clause short-circuits, so `CREATE INDEX IF NOT EXISTS` naming an index that
  already exists still raised `InsufficientPrivilege` for a non-owning role.
  The DDL that would change nothing was exactly the DDL that refused.

  Measured against a live cluster as a member of a grant role that owns
  nothing: `SELECT`/`INSERT` OK, `CREATE INDEX IF NOT EXISTS` and
  `ALTER TABLE ADD COLUMN IF NOT EXISTS` both `must be owner of table ...`.

  Ownership is again a requirement for CREATING a store rather than for using
  one, which is what the grant model already assumed.

### Added

- `Dialect.indexes_sql` — the index counterpart to `columns_sql`, same
  contract (first column is the name, no rows for a missing table);
  `pg_indexes` on PostgreSQL.
- `Dialect.index_specs` / `Dialect.schema_tables` enumerate what `create_sql`
  builds, and `create_sql` now emits its `CREATE INDEX` statements from that
  list — one list, two readers, so the probe and the creator cannot drift.

### Notes

The probe is conservative: any missing table or index runs the full
`create_sql` exactly as before, so it can only remove DDL that would have
changed nothing.

## [0.56.1] - 2026-08-20

> **The audit was reading a different tree than the one it said it was
> auditing** — and the workflow the fleet is *required* to use was the one way
> the resulting failure could not be diagnosed before merge. Plus the cron
> retirement could not complete on the one host that still had a block.

### Known issue — please read before assuming it is your change

`ecosystem audit-all` has **crashed once with SIGSEGV (exit 139)**, on CI,
mid-audit. It is not a finding: the process died. On the PR page a crashed
gate and a failed gate are the same red, so the natural reading is "my change
broke the audit". It was not, and it will not be yours either.

**It is confirmed nondeterministic.** The same merge tree was audited twice —
once crashing, once clean — with the base branch provably static between the
two runs. It then survived 15 further runs on the machine that crashed
(CI's merge tree, current develop, and memory-capped variants), never once
reproducing.

So *"I could not reproduce it"* tells you nothing. It is what everyone gets.
Cause unknown; C-stack overflow, cgroup OOM, allocation failure and job
concurrency are each excluded by measurement. If you hit it, please attach the
`PYTHONFAULTHANDLER` traceback (see below) rather than re-running until green.

### Fixed

- **§6a read its exemption from a different tree than it audited.**
  `audit-cli` prints `auditing <tree> (via cwd)` and then resolved the
  package's `env_allowlist` *without passing that tree*, falling back to a
  resolver that prefers the **import** location — which, with an editable
  install, is the main checkout while the audit is auditing a worktree.
  Measured by scitex-cards: the same call returned their declared allowlist
  when given the worktree and `()` on the audit's own path.

  The contributor had added the entry correctly and §6a stayed red, with no
  way to tell "my exemption is wrong" from "my exemption is unreadable from
  here" — and the message's advice was the thing they had already done.
  **This is the sanctioned workflow**: fleet hooks require tracked edits in a
  linked worktree, so the only supported way to declare a §6a exemption was
  the one way it could not be verified before merge.

  Confirmed end-to-end on a real repository after the fix: with the install
  pointing at the audited tree, their §6a finding went 1 → 0 and §4 went
  7 → 0 *without a character of their `pyproject.toml` changing*.

- **`repo` is now a required argument at all four exemption readers**
  (`read_pkg_env_allowlist`, `is_mcp_parity_exempt`, `declares_no_mcp`,
  `mcp_tools_allowlist`). All four already ran the identical resolver, so
  "use the audited-repo resolver" was **true at the site where the bug was**
  and could never have caught it. The condition that can fail is *being called
  with* the audited tree, and a required parameter makes forgetting impossible
  rather than merely discouraged. Passing `repo=None` still selects discovery
  and now states that as a decision.

- **The cron retirement could not write on a host that still had a block.**
  `crontab -` refuses input without a trailing newline, so retirement failed
  on the only host it still had work to do on, while hosts with nothing to
  remove reported success. The has-a-block predicate was also wrong: it
  compared stripped output to the original, which is equal on hosts that never
  had a managed block.

### Changed

- The audit job sets `PYTHONFAULTHANDLER=1`, so a crash prints its C-level
  stack and Python frame to stderr (unbuffered, therefore surviving SIGSEGV).
  The one real occurrence left no evidence at all: no core (the runner's
  `RLIMIT_CORE` is 0), no traceback, and no log body — `audit-all` prints
  nothing for ~17s and then everything at once, so a crash 1.74s in logs
  nothing regardless of buffering.

### Documentation

- Resolution precedence between the import location and the registry is now
  stated in `_audited_repo_root` **and nowhere else**. It had been restated in
  prose in two docstrings, the implementation was later reversed under both,
  and a reader met the same stale sentence twice and reported the second
  reading as *confirming* the first. Two copies of a claim are not two
  sources: a duplicated explanation does not merely risk going stale, it
  manufactures false agreement in whoever checks it.

## [0.55.0] - 2026-08-18

> **The supervisor owns the clock, and the auditor comes from the environment
> under test.** Two structural fixes that were merged but unreleased — which,
> by the operator's standard, means they did not exist: 「ライブでない機能は
> ないものとカウントします」.

### Added

- **The supervisor runs periodic jobs itself.** Timer- and cron-kind jobs were
  lowered to user-crontab lines; the operator ruled that out (20+ lines per
  host does not scale). They are now one-shots started on the supervisor's own
  tick — which is the real difference from a service child: a service that
  exits is a fault to restart, a periodic run that exits is a success.
- **An execution log that records what SHOULD have run.** `started` /
  `finished` / `start_failed` / `skipped_still_running` / `unschedulable`, one
  JSON line each, every line naming its host. The last event has no other
  witness: a job that never started is indistinguishable from a healthy quiet
  system unless something wrote down that it was supposed to run.
- `scitex_dev.testing.auditor_identity` — the failure report now names WHICH
  auditor measured the tree, asked of the launcher rather than of this process,
  and returning an explicit `UNKNOWN (path) — could not ask: …` rather than a
  plausible default.

### Fixed

- **The auditor was resolved from shell PATH.** `audit_all_for_package` and
  `audit-all`'s six-sub-auditor fan-out both used `shutil.which`, so the rule
  corpus a test graded against was decided by whichever binary was earliest on
  PATH. Measured by scitex-agent-container: same tree, auditor 0.49.2 reported
  PS-226 while 0.54.0 reported PS-140/PS-226/PS-231 — and the PATH entry
  resolved through a wrapper into ANOTHER PACKAGE's venv. Worse than a stale
  install because it DEFEATS THE OBVIOUS FIX: upgrading the venv under test
  changes nothing, so the correct experiment disproves a true hypothesis. Both
  layers now launch via `sys.executable -m scitex_dev`.
- `--new-only` is **FORBIDDEN** (operator ruling). It capped pre-existing
  findings to warning, which let a package stop honouring a shared rule without
  anyone deciding to, while the gate kept reporting green against a smaller
  rule set than it claimed to enforce.
- The `0 unmasked error(s)` + `exit=1` note named ONE cause of at least two,
  and a reader acted on it by proposing to relax the gate for 83 packages.

### Notes

- A pre-push hook test was GREEN BECAUSE THE SUB-AUDITORS COULD NOT LAUNCH
  under its deliberately sterile PATH. Fixing the resolution made them run, and
  an ordinary INFO line tripped a loose substring assertion. A test going red
  because a fix started working.
- Four test harnesses selected their auditor BY PLANTING A SHIM ON PATH — they
  depended on the defect. `audit_all_for_package` now takes `launcher=` so a
  test NAMES its auditor instead of arranging for the environment to answer.

## [0.54.0] - 2026-08-18

> **Three surfaces were telling readers something that was not so, and every
> one was caught by a peer rather than by this package's own tests.** A gate
> generator emitting the shape its own rule forbids; a failure headline whose
> code census was read as the causal list, sending one repo's lead to two
> teams with "structurally blocked"; and a remedy that instructed a package to
> delete working behaviour to quiet a warning that gated nothing.
>
> **The release matters more than the fixes.** `assert_imports_tree_under_test`
> and the corrected generator both sat on `develop` where no leaf could install
> them — leaves pin `scitex-dev>=0.12.2` against PyPI, so the helper was merged
> and *uninstallable*. Present, correct, and unreachable is worse than absent,
> because it looks identical to adoption lag from the board.

### Added

- `scitex_dev.testing.assert_imports_tree_under_test` /
  `make_pytest_configure` — refuse to run tests when the imported package
  resolves OUTSIDE the tree under test. Contributed by figrecipe after the
  confound was measured four times in one day across two agents, including a
  run here reporting **1049 passed** against `site-packages` rather than the
  worktree just edited. Both authors hit it *after* writing warnings about it,
  which is why it is a mechanical guard and not a documented practice.
  Compares fully `resolve()`d paths so editable installs, linked worktrees and
  `--target` layouts are accepted; refuses only what is provably outside.
  Opt out with `SCITEX_ALLOW_FOREIGN_IMPORT`, which announces itself loudly on
  stderr — an opt-out that hides itself is the defect wearing the fix's
  clothes.

### Fixed

- **`ecosystem write-integration-tests` emitted a gate that cannot PASS.**
  `DEFAULT_GATE_TAIL` produced a bare `importlib.import_module` with no skip —
  the exact pole PS-140's own docstring names as the opposite face of the bug
  it fixes ("a gate that cannot PASS, in place of one that cannot FAIL"). A
  lean install where a peer is legitimately absent failed. Now emits
  skip-on-ROOT + hard-import-FULL. Reported by figrecipe (lean install) and,
  from the opposite pole, by scitex-ui (mutation: a renamed submodule reported
  green). **Three tests had pinned the bug in**, one of them stating the
  correct three-valued distinction in its own docstring and then asserting a
  substring check that collapsed it. Tests now grade against
  `find_full_path_skips` — the function the audit itself runs.
- **The audit failure headline listed a census, not a cause.** It named every
  rule code appearing in findings, so a run failing on two of six read as
  blocked by all six. Now splits by TIER and carries the count:
  `PS-140, PS-231 (6 finding line(s)) — also reported at warn/info tier: ...`.
  Deliberately **not** labelled gating/non-gating: this runs outside the
  audited process and holds only its stdout and one exit code, so which
  findings drove the exit is unknowable here — and warn-tier findings *do*
  gate in some sub-auditors. The note beneath now says so outright.
- **§12/§13 prescribed a remedy that costs behaviour.** Both offered
  `deprecated_alias()` unconditionally; it forwards argv and nothing else, so
  a leaf whose alias accepted options the target lacks silently lost them.
  Measured on figrecipe: `start-gui --force` (kills the port holder) became a
  usage error. The caveat now lives in one shared constant used by both rules.
- **PS-231's conversion advice could brick the repo following it.** Filed P1
  by scitex-hub, measured independently by hub, scitex-scholar and scitex-app:
  calling an org reusable renames the published check context, branch
  protection keeps requiring the old name, and no pull request can fix it. The
  finding text now says to enumerate required contexts **per protected
  branch**, admits **the rule cannot check this itself** (the fact lives
  behind a different API — `audit` is required on figrecipe and not on
  scitex-app from identical-looking files), and names the third failure mode:
  a caller that publishes but can never succeed, which shows as an ordinary
  red.
- The guard now **speaks when the package cannot be imported at all**, rather
  than surfacing a bare `ModuleNotFoundError` that names neither the tree
  under test nor the fact that a guard was running.

### Notes

- PS-231's remedy text had **never once been constructed** in 7115 passing
  tests, and structurally could not be: scitex-dev *provides* the org
  workflows, so the rule cannot fire on its own package and its message is
  exercised only in other repos' CI. Three tests now force construction.
- The generator fix reaches only files that do not exist yet. Regeneration
  preserves each gate's tail **byte-identically by design**, so the 19
  deployed gates keep their old assertion until swept deliberately. Tracked
  separately; the sweep cannot be done by regeneration.

## [0.53.0] - 2026-08-18

> **The job renderer can now express what a real unit says.** Four properties
> were previously *decided by the renderer* rather than declared by the job,
> so a hand-written unit that disagreed could not be adopted without silently
> changing meaning — which is why 123 of 184 fleet units were not
> verbatim-safe to adopt.
>
> The expensive one is `EnvironmentFile=`. It is frequently the only on-disk
> record of where a daemon's configuration and secrets come from, so a
> renderer that could not express it did not lose a line — it started the
> daemon with an **empty environment while the unit still reported
> `active`**.
>
> **Existing jobs are unaffected.** Every new field defaults to unset, and
> unset renders exactly as before: all 34 discovered jobs render
> byte-identically against the previous renderer (31210 bytes both sides).

### Added

- `JobSpec.service_type` — systemd `Type=` for `kind="service"`. Previously
  hardcoded to `simple`, or `notify` when a watchdog was requested, so a
  daemon declaring `Type=exec` could not be adopted without changing when
  systemd considers it started.
- `JobSpec.remain_after_exit` — `RemainAfterExit=`. Previously hardcoded to
  `no`, so a unit whose *effect* outlives its process reported `inactive`
  the instant it succeeded.
- `JobSpec.working_directory` — `WorkingDirectory=`. Previously derivable
  only from `venv`. An explicit value now wins over the derived one.
- `JobSpec.environment` / `JobSpec.environment_file` — extra `Environment=`
  entries and `EnvironmentFile=`. Explicit entries are emitted *after* the
  venv-derived `VIRTUAL_ENV=`, so a leaf can deliberately override it.

### Changed

- A contradiction is now **refused at construction rather than reconciled**:
  `watchdog_sec` together with a non-`notify` `service_type` raises, because
  the watchdog protocol exists only under `Type=notify` and the pair would
  emit a `WatchdogSec` that can never be satisfied — restarting the daemon
  every interval. `service_type` is likewise refused on a timer (its body is
  always a oneshot) and all four on cron.
- The cron lowering classifies each new field explicitly and **detects** it
  rather than merely listing it: `working_directory`, `environment` and
  `environment_file` are blocking losses (each decides what actually runs),
  `remain_after_exit` is advisory (it shapes `systemctl is-active` only, and
  nothing reads that for a crontab line).
- Internal: `JobSpec` moved to `jobs/_spec.py` and cadence/ExecStart
  resolution to `jobs/_resolve.py`. Both modules re-export their previous
  names, so no import changes. These were not tidying — `jobs/__init__.py`
  (516 lines) and `_systemd.py` (564) both exceeded the repo's 512-line
  limit, so the fields above could not be added to them at all.

### Fixed

- `ecosystem up`'s abort path now carries out the degraded count that caused
  it, instead of aborting without reporting the number.

## [0.52.0] - 2026-08-18

> **Backfilled.** This entry was written after the fact — 0.52.0 was tagged
> and published without one, so the release that unblocked several packages
> had no record of what it contained. Reconstructed from the nine merged
> pull requests between `v0.51.0` and `v0.52.0`, not from memory.
>
> The consequential change for other packages is the hooks `provider` fix:
> it cleared a `HookRule` `TypeError` that had been failing every branch
> across the fleet. Downstream CI that resolves `scitex-dev>=0.52.0` picks
> that up automatically.

### Added

- `JobSpec.on_calendar` — a timer can name a **wall-clock time** with a
  timezone. Previously `schedule=` was derived to an interval, so any
  wall-clock anchor in it was discarded; that discard is now **loud**,
  naming the job, the discarded fields, what it became, and the remedy.
  Only anchored expressions warn; the existing derivation is unchanged.
- Service **stop semantics** on `JobSpec`: `kill_signal`, `kill_mode`,
  `timeout_stop_sec`, `exec_reload`, `exec_stop` and
  `restart_prevent_exit_status`. systemd's default stop is SIGTERM then
  SIGKILL, so a daemon wanting SIGINT was hard-killed and recovered as if
  it had crashed. `RestartPreventExitStatus` lets a process that says
  "do not retry" be believed.
- The installer uses **uv**, and a timer keeps the shared dev venv current.
- Skills documenting the state-store contract, cross-host identity, and
  worked examples.

### Fixed

- Hook discovery stamps `provider` itself, because discovery already knows
  it — this is the fix that cleared the fleet-wide `HookRule` `TypeError`.
- `not-auditable: unknown` now names the interpreter instead of reporting
  `unknown`, so the cause is actionable.
- The interpreter `bin/` probe no longer follows the venv symlink, which had
  resolved out of the venv into the managed toolchain.
- scitex-dev's own timers and the last three federation job names are
  **package-qualified**, so a job name states which package owns it.

## [0.51.0] - 2026-08-17

> **This release adds two audit rules and removes three CLI verbs.** A repo
> can go from green to red on this upgrade with no diff of its own, for the
> same reason 0.50.0 could: PS-231 (a leaf workflow that re-implements an
> org-provided reusable) and PS-140 (an import gate that skips on the full
> path, so a rename is silently skipped) both fire on code that was passing
> yesterday. Measured on three packages: scitex-writer 6 of its 7 total
> errors are PS-231, figrecipe 5 of 6, scitex-cards 8.
>
> Consumers of the org `quality-audit` reusable remain **pinned to
> `==0.49.3`** and will not pick this up automatically. Bump that pin
> deliberately.
>
> **Removed CLI verbs:** `ecosystem dashboard`, `ecosystem start-dashboard`
> and `gui start` no longer resolve. They were Phase W aliases declaring
> `remove_in="0.34"` and this package is at 0.50. Use `gui`, `gui open` and
> `gui watch`.

### Added

- **PS-231 — a leaf workflow that RE-IMPLEMENTS an org-provided one (#615).**
  A local copy does not track fixes made to the org workflow: the
  `scitex-ci` runner-label defect was fixed org-side on 2026-08-15 and every
  copy kept it. Names the caller form and the exemption path.
- **PS-140 — a gate that skips on the full path cannot catch a rename
  (#647).** `importorskip(full.dotted.path)` turns a renamed submodule into
  a SKIP that reports green — the exact failure the gate exists to catch.
- **Fleet-wide exemption census, and `list-exemptions` (#642, #645).** Every
  exception, plus how much of the fleet could not be read — an exception
  nobody can see is one that never gets retired.
- **Process currency — ask whether a RUNNING process predates the code it
  claims to run (#659), and say when a version number describes a different
  moment than the code (#651).** Merged is not live; fresh on disk is not
  fresh in memory.
- **Federated agent guardrails, written down (#592).**
- **`scitex-vpn` registered as a leaf (#633).**
- **The cross-package gate dates itself, and has tests (#640).**

### Fixed

- **This repo's own audit gate could not fail (#650)**, and **the gate that
  grades every package could not tell which tree it graded (#662)**.
- **PA-306 walked a FOREIGN `tests/` tree and called it your verdict
  (#652).**
- **The untrustworthy-install check inspected 3 of 70 packages (#653)**; the
  banner now names the interpreter (#657).
- **`validate-versions` never asked whether it could believe the versions
  (#656).**
- **`drift-report` read the ref the label names, in both reference columns
  (#661).**
- **A fence must never arrive on the data it authorises (#584).**
- **Regenerating a gate must not eat what a human wrote in it (#644)**, and
  everything below the sentinel is preserved byte-identically (#641).
- **`kind="periodic"` with a `schedule` is refused rather than guessed
  (#666).** A schedule does not identify the scheduler — a systemd timer may
  carry one as an OnCalendar fallback, and seven live sac declarations do.
  Guessing silently moved such a job from systemd to crontab.
- **Locality is computed from this machine, not declared in the file
  (#580)**; the laptop's MEASURED ssh alias is recorded (#616).
- **A synthetic root must not be judged by the machine running the test
  (#660).**
- **The merge gate ships with the tool — the file-copy version was lost,
  silently (#634).**
- **The quality-audit workflow name is neutral, not a package name (#638);**
  the generated gate stops tripping STX-TQ007 (#636) and says it will be
  overwritten (#637).
- **A verdict names its own subject and says what it read (#654, #655).**
- **`scitex_todo` import name retired from cron (#643).**
- **`audit` names the verb, and a dry-run proves which code is running
  (#646).**

### Changed

- **The real-host invariant is a signature, not a comment (#665).**
- **`scitex-orochi` is archived in the ecosystem registry (#668).** Retired
  by the operator 2026-08-16 (「サイテクスオロチはもう使わない」); the
  registry did not know, so every brand-wide sweep still enumerated it.
  `archived: True` — the existing field every auditor already honours —
  rather than deleting the row: the repo and the published distribution
  still exist, and deleting would blind sweeps to something still out
  there. Archiving is not yanking.

### Removed

- **The Phase W dashboard aliases (#667)** — see the note above.
- **`doctor`'s Orochi connectivity check (#668).** A probe of a
  decommissioned system: a check whose failure means nothing.

### Docs

- **ADR-0008 records the ruling, so the standard can be cited (#663).**
- **The §13 federation paragraph described a capability that does not exist
  (#664).**
- **A sibling that is a DECLARED dependency must not be `importorskip`'d
  (#639);** why `_install_kind` and `_install_probe` must not be merged
  (#658); which class of state the runtime-state-DB layout governs (#648);
  The embedded engine is eradicated, so the `.db` layout is marked historical (#649).

## [0.50.0] - 2026-08-16

> **This release moves the rule corpus.** `_fd.py` changes which files every
> rule sees, and PS-224's checker, the job-naming check, and the masking and
> verdict layer all changed with it. For an audit gate the corpus *is* the
> definition of passing, so a repo can go from green to red on this upgrade
> with no diff of its own — scitex-hub measured exactly that on 2026-07-28,
> when an identical tree audited green and then red across a release.
>
> Consumers of the org `quality-audit` reusable are therefore **pinned to
> `==0.49.3`** (scitex-ai/.github#36) and will not pick this up automatically.
> Bump that pin deliberately, as a reviewable change, rather than inheriting a
> new corpus from someone else's release timing.

### Added

- **`scitex_dev.measure.require_match` — an unmatched read is an unanswered
  question, not an empty answer (#626).** Raises on no-match, and *also* on
  multiple-match-without-`identity`: `tail -1`/`head -1` are not selections,
  they are guesses about ordering, and a log holding two generations answers
  both confidently and wrongly. `identity=` narrows to the right instance (a
  date, a run id, a pid). Built from thirteen measured instances across three
  packages in one day — a `gh api` 404 body defeating an emptiness test (76
  repositories recorded as having a variable when 8 had none), `command -v`
  under a PATH without `/sbin` reading an installed binary as absent, a regex
  that could not cross the "i" in "warnings". Documents what it cannot catch:
  a true answer to a question you did not realise you were asking.

- **Runner liveness probe — registry membership is not liveness (#619).**
  `classify_label` answers SERVED / UNSERVED / UNKNOWN by superset match
  against *online* runners and names the carriers, so a "served" answer is
  checkable. UNKNOWN does not block: an unreachable API is a broken
  instrument, not an outage. Measured 2026-08-15: 49 repositories pinned
  `spartan-cpu`, 80 workflow references fell back to `scitex-ci`, every org
  runner carrying either label was offline — and PS-224 reported nothing,
  correctly, because both labels *are* in the registry.

- **CI coverage classifier — a green PR is not a checked PR (#624).**
  `classify_pr_coverage` returns COVERED / UNCOVERED / UNKNOWN and names the
  required checks that never reported. Green means "nothing required FAILED",
  not "everything required REPORTED", and GitHub renders those identically:
  a PR based on a topic branch matches no `pull_request: branches:` filter,
  so nothing runs and nothing is red. Keeps "unreachable base" as its own
  field — retargeting a PR and diagnosing a workflow that failed to start are
  opposite investigations.

- **Declared auditor exit policies (#625).** The sub-auditors do not share
  one, and the downgrade logic was guessing. Read from source, not docstrings:
  `audit-project`/`audit-django` are ERRORS_ONLY, `audit-skills`/
  `audit-python-apis` are ANY_FINDING, `audit-cli` is WARN_ONLY (it never
  exits non-zero). `failing_audit_is_explained` asks each failing auditor the
  question its own policy makes meaningful — identical output, opposite
  answers for `audit-project` and `audit-skills`, which one shared question
  cannot express. An auditor with no declared policy is not downgradeable:
  an undeclared policy is an unasked question.

- **PS-232 — a JobSpec scan that graded nothing now says so (#623).**
  `check_job_naming` opened with a bare `return` when the source package could
  not be resolved: zero files examined, zero violations reported, and
  indistinguishable downstream from "scanned it, all clean". Scoped to repos
  that *claim* to be distributions (a `pyproject.toml` present), so a
  directory that never promised to be a package stays silent.

- **Hosts can request an address, and the sweep is honest that asking is all
  it does (#591).**

### Fixed

- **A run that inspected ZERO lines has no verdict, and now says so (#620).**
  `MaskReport.inspected` is the denominator — "0 unmasked error(s)" means
  nothing without it — and `decide_pkg_exit` never read it, so a run that read
  nothing still returned a pole, whichever one the dispatcher happened to hand
  it. Measured on the CI SIF's baked `scitex-dev` 0.42.0: `EXIT=1` with
  "0 unmasked error(s), 0 masked by skip-rules (1 declared); 0 line(s)
  inspected" — it inspected nothing, masked nothing, and still failed, which
  is a gate returning the failing pole by default rather than by measurement.
  Now non-zero with a named NO VERDICT message saying it is neither a clean
  result nor a real failure, and what to check. It stays RED rather than going
  green on purpose: the fix for a silent red is a loud red, never a silent
  green. Also closes the more dangerous direction the old code allowed without
  comment — `pkg_exit == 0` with zero lines read returned a clean bill of
  health from an instrument that never took a reading.

- **`Path.exists()` does not swallow errors, and calling an unstattable
  target ABSENT is dangerous (#622).** `evaluate()` called it outside its
  try/except; `_ignore_error` has never covered EACCES, so a spec under a
  root-only directory raised and aborted the whole `host-config apply` CLI
  before it printed anything. ABSENT is the state `apply` CREATES — the old
  behaviour would have called a root-owned file missing and then written it.
  Now DRIFT. It failed on exactly one runner, the only machine with `auditd`
  installed and `/etc/audit` at `drwxr-x--- root:root`, which is why it read
  as a flaky per-leg failure for hours; the discriminator is the spec's
  `requires_command` precondition, inert wherever auditd is absent.

- **The two file walkers must return the same set (#621).** `fd_find_files`
  shells `fd` when present and falls back to a stdlib walk when absent — and
  `fd` ships on developer machines but not everywhere, so the two paths split
  along an environment boundary. Measured: 1142 files against 1227 on one
  tree. The fallback now applies fd's own exclusions (hidden paths,
  gitignored paths) by asking git, with `--no-index` — `check-ignore`
  suppresses TRACKED files by default, which accounted for 83 of the 85.
  Equality is now asserted by test. The fallback warning was reworded from a
  speed notice to a correctness one: it was true and named the wrong
  consequence.

- **A declared skip rule now clears the exit status, not just the report
  (#590).** `ecosystem audit-all` masks findings on rules a repo has declared
  in `.scitex/dev/config.yaml`, prints the masked inventory, and prints a
  summary line stating how many UNMASKED errors remain. It could print
  `0 unmasked error(s) ..., 1 masked by skip-rules (1 declared)` and still
  exit 1 — a gate whose report and whose status disagreed, and a deferral
  mechanism that did the one thing it exists for only sometimes.

  The downgrade was decided over the run's CONCATENATED output, which
  destroys attribution: a WARN-tier finding printed by an audit that EXITED 0
  landed in the same `unmasked` list as a real failure and vetoed the
  downgrade. Measured on scitex-agent-container — `audit-project` failed on
  one declared `PS-226`, three warnings came from `audit-cli` (exit 0).

  It is now decided PER AUDIT, against the audits that actually exited
  non-zero: each is asked "is everything YOU reported masked?". Severity is
  deliberately not the discriminator — `audit-skills` and `audit-python-apis`
  exit 1 on WARN-tier findings too, so an error-only predicate would have
  turned runs those two legitimately failed green. What is REPORTED is
  unchanged: the inventory, the labels and the summary are still computed
  over the whole run.

## [0.49.0] - 2026-08-12

**A declaration that resolves to something.** `scitex_dev.store` shipped in
0.47.0 with an oplog, a hybrid logical clock, per-origin cursors, field-level
HLC merge and a `MergeRule` enum — and zero callers, because the federation
layer that lets a leaf DECLARE a store was never on a branch. Two downstream
packages had already shipped their half of the contract against it: sac's
`[project.entry-points."scitex_dev.store.plugins"]` and scitex-cards' mirror
of it both resolved to a provider that RAISED `ModuleNotFoundError`. A
declaration that exists, passes inspection, and does nothing is worse than an
absent one, because it reads as done.

### Added

- **`scitex_dev.store` federation — leaves declare semantics, scitex-dev owns
  the machinery (#594).** The parent package now re-exports `StorePlugin`,
  `StorePluginProvider`, `discover_store_plugins`, `plugin_for`,
  `resolve_target` and `ENTRY_POINT_GROUP`. A leaf registers a provider
  (`() -> list[StorePlugin]`) under the entry-point group
  `scitex_dev.store.plugins`; `discover_store_plugins()` aggregates them,
  deduped by store name, first-wins.

  **Two strings are the pinned public contract** — the import path
  `scitex_dev.store` and the group name `scitex_dev.store.plugins` — and both
  are asserted by test (`tests/scitex_dev/store/test__exports.py`,
  `federation/test__discover.py`). Renaming either orphans every installed
  leaf SILENTLY: discovery finds nothing and reports an empty federation,
  which is indistinguishable from "no leaf has adopted the store yet".

  A leaf declares only the part it alone can know — which of ITS fields are
  immutable, last-writer-wins or append-only — because a merge rule guessed
  by scitex-dev would lose data without raising. It does NOT resolve its own
  store target: `resolve_target()` does that centrally, because per-consumer
  resolution is what let one host reach two Postgres instances that both
  answered to one `store_uuid` on 2026-08-11.

  `store/federation/` is shaped like `scitex_dev.gate` — `_spec` /
  `_discover` / `_builtin` / `_resolve` behind a pure re-export façade — so
  the three federations are one thing to learn. It carries both of `gate`'s
  seams, `include_entry_points` and `include_builtins`, which
  `scitex_dev.jobs` lacks: without them a test can only assert
  set-membership, because any installed leaf leaks into the result and makes
  it depend on the environment.

  scitex-dev registers its OWN store through an INTERNAL provider, never an
  entry point. It is a leaf of this federation, not a privileged parent, and
  a package that registered in a group it also reads would have discovery
  load scitex-dev's metadata to find scitex-dev.

- **An empty federation says WHY it is empty.** An installed-but-unregistered
  leaf and a typo'd store name produce the same empty result, so
  `plugin_for()` distinguishes them in prose rather than returning `None`
  twice. Every failure of 2026-08-11 was a truthful empty answer about the
  wrong thing.

- **Store identity, divergence detection and a dialect
  split** (`store/_identity.py`, `_identity_state.py`, `_divergence.py`,
  `_dialect/`). The identity layer is what makes "two instances answering to
  one `store_uuid`" detectable instead of silently merged.

### Fixed

- **`rm -rf ""` is a silent success, so the CI scratch path is guarded with
  `:?` (#586).** An unset or empty scratch variable expanded to a bare `rm
  -rf` that removed nothing and exited 0 — a cleanup step that could not
  fail, and therefore could not report that it had never run.

## [0.48.0] - 2026-08-12

Published from the develop→main promotion (#574) without a CHANGELOG entry;
this section is written after the fact from the tag range `v0.47.0..v0.48.0`,
because the release contained two BREAKING changes for downstream consumers
and shipping them unannounced is what made them expensive.

### Changed (breaking for downstream consumers)

- **One CLI group per JobSpec KIND, not per mechanism (#566).** `ecosystem
  dev {service,timer} <verb>` replaces the previous per-mechanism surface.
  The name argument is MIXED by design — `install`/`uninstall` take
  `--name X`, while `status`/`enable`/`disable`/`start`/`stop`/`restart`/
  `exec` take a POSITIONAL name — so any caller emitting `--name`
  unconditionally now dies with `Error: No such option '--name'` (exit 2).
  Measured downstream: nine sac commands, and the reason sac holds a
  `scitex-dev<0.48` ceiling.

- **PS-226..PS-229 — the fleet-wide JobSpec declaration convention (#565).**
  PS-226 `job-name-not-hyphenated` does not exist in 0.47.0 at all (0
  occurrences in the 0.47.0 wheel, 6 files in 0.48.0). A new `E`-severity
  rule lands as an unmasked error in every downstream `audit-all` gate the
  moment the dependency floats, which is a release-note-worthy event even
  when the rule is right.

### Added

- **`sac-control-plane` is a registered runner destination — the label was
  real, nothing declared it.** The shipped seed gains `scitex-compute-04`
  (`kind: compute`) with the effective label set its one runner carries:
  `[self-hosted, Linux, X64, scitex-org-cpu, sac-control-plane]`, measured
  2026-08-12 from the org Actions API and from that machine's own
  `~/actions-runner-org/.runner`.

  sac's CI feedback rail pinned a `verdict` job to `sac-control-plane` and
  PS-224 refused it. The rule was right. sac's ADR-0024 had assumed the
  self-hosted runners execute on the host running the control plane; they are
  four runners on four machines, and only `scitex-04-org-cpu-01` shares one
  with `sac listen` (`127.0.0.1:7878`) and the card store
  (`127.0.0.1:55432`). Both bind loopback, so on the other three that job
  calls a different machine's daemon and writes to a different postgres —
  delivered to nobody, recorded nowhere, and green either way. The pin is
  necessary while those services are loopback-only.

  Registered rather than exempted, deliberately. A PS-224 exemption was
  considered and rejected: the single existing one in the ecosystem rests on
  a security argument, and an exemption granted because a rule is
  inconvenient is how an audit stops meaning anything.

  What the entry records, in comments, because the registry schema has no
  field for a destination's MEANING: `sac-control-plane` is a CO-LOCATION
  claim, not a capability tier, and anything pinned to it is exactly as
  available as that one machine — it does not fail over, and PS-224 will
  still pass it, because the gate validates served-ness and not capacity.
  Registering the runner's EFFECTIVE set also makes the broader
  `scitex-org-cpu` destination legal; its three sibling machines
  (`scitex-01/02/03-org-cpu-01`) are not registered yet, so that destination
  is legal on the strength of one entry and under-reports the pool by three.

- **A check verdict is THREE-valued, and `unknown` has to say why (ADR-0010).**
  `scitex_dev.status` gains `Verdict` / `Check` / `rollup` beside `StatusCode`.
  The fleet's shared doctor shape — `{package, ok, checks: [{name, ok, detail,
  hint}], summary}` — carried a BOOLEAN `ok`, so "I could not find out" had to
  be filed as either "fine" or "broken", and both are false.

  Measured 2026-08-11: nine relocation probes were refused `http 403` by hosts
  running a daemon too old to have the endpoint. That 403 is real and it is not
  an answer to the question asked. Read as `not-ok` it grounds nine healthy
  agents; read as `ok` it moves an agent onto a host nobody inspected. The same
  day the card-store doctor could not open its store and reported `ok: false`
  on two checks whose questions it never got as far as asking.

  The purest form of it: an auto-merge sweep whose greenness filter dropped
  QUEUED checks counted "not yet known" as "passing" and merged unverified code
  past branch protection with `--admin`, in two repositories independently.
  Nobody decided that unknown was ok — a boolean filter over a three-state world
  did it for them, in one expression. It does not take a decision to get this
  wrong, only a boolean, which is why `Verdict.from_ok` refuses truthy
  stand-ins rather than coercing them.

  `unknown` must carry a reason and a way to find out, enforced at BOTH doors —
  `Check.unknown(name, reason, hint)` takes them positionally, and
  `__post_init__` refuses a blank one, so the dataclass constructor cannot get
  around the classmethod. A rule enforced in one place holds until someone uses
  the other door.

  The rollup policy is REQUIRED with no default: `refuse` (never act on a host
  you could not inspect), `propagate` (this report cannot say the whole is
  healthy) or `tolerate` (may I proceed?). A default here would be the same
  collapse a boolean is, moved one level up and made harder to find. Under
  every policy the summary NAMES the unknown checks.

  The wire form is unchanged: the verdict rides in the existing `ok` field as
  `true` / `false` / `null`, so the four-key report and four-field check record
  every existing reader parses keep working, and there is no second field that
  can disagree. `Verdict.from_ok` refuses truthy stand-ins — `bool(x)` is the
  one line that has eaten the third state everywhere it was lost.

  The idea was not missing: `versioning.Currency`, `store.StoreStatus`,
  `testing._audit_outcome`, `hygiene.Landed` and `_cli._doctor`'s
  `Literal["ok", "fail", "skip"]` are five separate three-valued verdicts,
  none readable to the others. This adds the one leaves publish. Nothing is
  migrated by this change; convergence is per-consumer, as ADR-0007's boundary
  declarations are.

### Fixed

- **The audit gate's first line now names the rules that fired (#593).** pytest's
  `short test summary info` carries one line per failure, and it is what CI
  notifications and `gh pr checks` triage are built from. That line read

      AssertionError: audit-all reported violations for 'sac' (exit=1).

  for every rule in the corpus — a CONSTANT, so two unrelated failures were
  indistinguishable without downloading each job log. The codes were already in
  the captured output, roughly four screens into the assertion body.

  Measured 2026-08-12 on scitex-agent-container: seventeen PRs red, all showing
  that one sentence, escalated as a P1 fleet-wide CI outage and given two
  published root causes before anyone opened a raw log. The real causes were
  four DIFFERENT rules — `PS-140` twice (different new modules), `PS-207`,
  `SK-302` — every one PR-local and a one-line fix by its own author.
  `audit-all` on develop exited 0 throughout. It now reads

      audit-all reported violations for 'scitex-dev' (exit=1): PS-207, SK-302, §1f

  Purely additive: the digest, the warn-tier note and the full stdout/stderr all
  still follow. Attribution reuses the masking classifier's structural
  discriminator ("the bracket carries a digit or `§`"), so the legacy
  `[E] [PS-207 …]` shape yields `PS-207` and not `E`, and a new rule family needs
  no edit. Codes are sorted and de-duplicated — output order is a thread-pool
  race, and one rule firing on four modules is one thing to go fix.

- **`summary: … 0 unmasked error(s)` no longer reads as a verdict on a red run
  (#593).** `audit-skills` fails on ANY finding; `audit-project`'s `--severity`
  floor is documented as "W/I findings never fail CI on their own". So a
  W-severity `SK-302` sets the exit code while the summary reports zero errors —
  measured with ZERO skip-rules declared, so this is not the masking defect and
  the count is not wrong. What was wrong is that the line reads as the verdict.
  `render_summary` now takes the package's own exit code and, in the one shape
  where the numbers alone mislead, says `— but this run EXITED 1: … This line is
  a TALLY, not the verdict`. `exit_code` is required and keyword-only for the
  same reason `inspected` is: a dropped argument silently restores the
  misleading line. The exit-code SEMANTICS are untouched — the asymmetry is
  deliberate on both sides and changing it is a separate call.

## [0.47.0] - 2026-08-11

**Six reports that were literally true and read as their opposite.** 0.44.0
and 0.45.0 fixed gates that said "fine" about runs in which they measured
nothing. This release is the same theme at full extent: a summary counting
a different population than the table above it, an `ERRO` on a finding that
cannot fail the gate, a rule firing on 426 things it was never aimed at, a
registry serving routes decommissioned four days earlier, and a version
string that killed a CLI at import while its own docstring promised render
time.

Every one was found by a peer measuring something, and several by peers
correcting me. scitex-storage, dotfiles and sac between them supplied the
measurements for all six.

### Fixed

- **PS-221 exempts the `dev`/`docs` TOOLING class (#554).** Not a new
  exception — a clause of the operator directive PS-221 implements and had
  dropped, which PS-217 quotes verbatim in its own finding text. The
  reductio is the rule's own prescribed remedy: closing them under `all`
  puts pytest and sphinx into every `pip install pkg[all]`.

  Measured fleet-wide before changing anything: of 113 packages with extras
  plus an `[all]` group, 49 had findings — **426 of 449 came from
  `dev`/`docs`, 23 from real feature extras.** A blocking `E` rule that was
  95% noise, gating the umbrella release. `scitex-io` 26 -> 0,
  `scitex-stats` 14 -> 1, `gPAC` 9 -> 6: scoped, not disabled.

- **The drift summary states its own scope (#555).** `validate-versions`
  printed `0/0 cells up-to-date` under a table with 45 of 68 rows marked
  drifted. Both numbers were right for the questions they answered — the
  summary counts REMOTE host cells, the `localhost` column is reference —
  but printed together they read as an answer to the question the reader
  asked. `summarize()` now carries `hosts_in_scope`, and the observe arm
  refuses to print a bare `0/0`.

  The exit code already knew (it requires `total > 0`), so every script
  wrapping this was fine and only humans were misled — which is why it
  survived.

- **A MASKED finding no longer prints as `ERRO` (#556).** The sub-auditor's
  output is echoed verbatim before masking is consulted, so a finding
  silenced by a declared skip still arrived labelled ERROR while being
  provably unable to fail the gate. The label now comes from the same
  `report.masked` that drives the exit code, so the two cannot disagree.

- **The host registry no longer serves RETIRED ssh routes (#557).** #551
  corrected the packaged seed; this reaches the registries already frozen
  on disk, which the seeder never rewrites. Measured in a live container: a
  month-old `hosts.yaml` with three dead routes and four missing compute
  hosts.

  A retired-NAME deny-list may be packaged where a route table may not: a
  retirement is monotonic, so the list can only ever be INCOMPLETE, never
  WRONG. Successors are read from the retirement log, not inferred —
  `nas -> scitex-nas-03` is exactly the pair a naming pattern gets wrong.

- **A version string no longer kills a source-checkout CLI (#559).**
  `render_help` raised `PackageNotFoundError` for a distribution with no
  metadata — and did it from `SpecGroup.__init__`, while the
  `@click.group` decorator was being evaluated. So the CLI did not degrade,
  it failed to IMPORT: `python -m <pkg> <anything>` was dead for every
  package adopting help_spec whenever run from a tree.

  The no-fallback rule is KEPT — no fabricated version, pinned by its own
  test. What changed is that "unresolvable" stopped being spelled "crash":
  the version has three states, and the middle one now says so out loud.
  The docstring had promised render time all along; the implementation
  exceeded it.

  Cost: it blocked the free-space alarm the 2026-08-09 compute-04 incident
  needed (364 MB free on 393 GB, nothing reported it) for two days.

### Added

- **PS-225 — extra names restricted to `{all, dev, docs}` (#491).** An
  operator ruling from 2026-08-02 that had been unmergeable for nine days,
  red on 17 remedy strings telling users to install extras the same branch
  deletes. Severity `W` during rollout per ADR-0005.

  The remedy strings were not merely misworded: every retired extra's
  backing package now lives in `[project.dependencies]`, so they offered to
  add capabilities that are already unconditional. They now name a broken
  install, which is what an absent core dependency actually means.

### Performance

- **The drift check's origin lookups run in parallel (#558).**
  `git ls-remote` per package, serially over 68 packages — ~170 seconds,
  paid even with zero hosts in scope. The `ThreadPoolExecutor` was already
  in the same function for the remote fanout and the origin loop never used
  it. ~15x faster.

  This is why two agents independently reported the command as "emits
  nothing" on 2026-08-11: neither had waited. Speed is the honest fix; a
  progress bar on a needlessly serial loop only makes the wait easier to
  sit through.

## [0.46.0] - 2026-08-11

**Two things that told the truth about themselves and were wrong anyway.**
A rule whose remediation text prescribed a config stanza the rule never
read, and a host registry that answered "how do I reach this machine" with
names ssh had stopped accepting four days earlier. Both are the same shape
as 0.44.0/0.45.0's theme — an answer that is confidently formatted and
does not correspond to anything — moved from REPORTING onto ADVICE and
ROUTE DATA.

Both were reported by peers who did the measuring: scitex-storage on both
counts.

### Fixed

- **PS-221 now honours the `audit.exemptions` stanza its own advice
  prescribes (#531).** The rule's text sent readers to write

      audit:
        exemptions:
          PS-221:
            - path: pyproject.toml
              line: <n>
              reason: "..."

  ...and PS-221 never consulted it. The mechanism was implemented,
  documented, carried a mandatory reason and was already wired into four
  other rules; this checker simply was not one of them. scitex-storage
  wrote the documented config, watched it silence nothing, and had to
  establish by experiment that the prescribed path was inert.

  That is worse than no advice. Advice that does not remediate costs the
  reader the work of following it PLUS the work of discovering it was
  never going to help — and it looks, to the next reader of the config,
  exactly like a handled exemption.

  The exemption pins to the offending REQUIREMENT'S LINE, not the file.
  Every PS-221 finding lives in `pyproject.toml`, so a `line: 0` entry
  would silence all of them at once — rule granularity wearing a per-site
  costume, which is the blanket shape `skip-rules` already offers and
  precisely what a per-site mechanism exists to avoid. A site the parser
  cannot pin returns the sentinel and stays VISIBLE: "cannot locate"
  must not degrade into "matches".

- **The shipped host registry served RETIRED ssh routes (#551).** The
  packaged seed hard-coded `ssh_alias: nas` / `nas1` / `nas2`, all three
  decommissioned on 2026-08-07 — they resolve to nothing by design,
  printing their successor and exiting 255. So for four days
  `scitex_dev.hosts`, the registry other packages resolve THROUGH instead
  of inventing their own host config, handed out routes that could not
  connect. A discovery SSoT with stale route data is worse than no
  registry, because consumers trust it.

  The successors are read from the retirement mechanism, not inferred:
  the stub logs `old=X new=Y` on every hit, and the top entry is
  `nas -> scitex-nas-03`, which is exactly the pair a naming pattern
  gets wrong. Still live at the time of the fix — scitex-orochi's
  five-minute liveness probe accounted for 1074 of the recorded hits.

  The old names survive as `aliases`, not as routes. `ssh_alias` is the
  ROUTE and had to change; `aliases` are LOOKUP KEYS, and a caller
  passing `nas` is using the name the fleet used until four days ago.
  Deleting them would have converted a stale-route bug into a resolution
  failure for every such caller. `HostRecord.aliases` was built for this
  case in #514 — the capability had shipped and the seed data was never
  migrated onto it.

## [0.45.0] - 2026-08-10

**Three checks learn to say what they did not check.** 0.44.0 fixed gates
that reported "fine" for runs in which they measured nothing; this release
is the same idea turned on the REPORTING side. A verdict now declares which
rule corpus produced it, a skipped-category notice stops describing itself
as silent, and a rule that was winning on measurement while losing on
argument now states the hazard it actually guards.

All three came out of one evening's exchange with scitex-db and scitex-hub,
who between them found: a container grading against a corpus that predates
the rule being tested, and a print-ban whose stated reason a competent
maintainer could beat.

### Added

- **A verdict states which rule corpus produced it.** `describe_corpus()` /
  `corpus_provenance()` in `linter/_health.py`, and it is UNCONDITIONAL —
  `describe_skips()` returns `[]` when nothing was skipped, so a run that
  skips nothing said nothing about which corpus graded it, and that silence
  was indistinguishable from a current, complete run.

  Measured: scitex-db's container carried scitex-dev 0.28.0, in which
  PS-220 does not exist at all (controls present, so genuine absence). Their
  local audits had been reporting clean for a rule that was not there. A
  rule that is ABSENT cannot fire at any severity — the most complete way
  for a check to be unable to fail.

  The module PATH ships beside the version, because the version is metadata
  and metadata lies: a stale wheel, an orphaned `.dist-info` and a SIF baked
  months ago all report a version that outlived the code beside them.
  AMBIGUITY IS REPORTED, NOT RESOLVED — two `.dist-info` dirs make the
  version a coin toss, so the line says AMBIGUOUS and lists both rather than
  picking one (measured on this repo's own container: `['0.38.0','0.43.1']`
  on the night 0.44.0 shipped).

### Fixed

- **PS-220 named the detector, not the hazard.** The finding said the call
  "prints human prose … this is a message". Prose is how the rule DETECTS
  the problem; it is not the problem, and on that framing the rule loses to
  anyone whose function legitimately renders a table for a human.

  The hazard is that LIBRARY CODE WRITES UNCONDITIONALLY TO STDOUT: a caller
  who imports the module cannot silence, redirect or capture it — no flag,
  no handler, no level. `log.info(...)` keeps the output for everyone who
  wants it and hands control to the caller. Behaviour is unchanged; same
  calls flagged, same calls spared.

  Worth stating because the weak framing had consequences: it lost an
  argument to scitex-db, who then supplied this reason against their own
  position and converted. A rule whose stated reason can be beaten is one
  people route around — the same "gets ignored" failure as too-low a
  severity, arriving by a different door. PS-220 defaults to `W`, so do not
  make it louder without also making it answerable.

- **The IO/PA notice called itself silent, and implied its gap was by
  design.** It said the checks "are SILENTLY skipped" while BEING the
  disclosure that they were skipped. And it never said whether the absence
  was a gap or a design choice — so "io/path is a research concern, this is
  a tooling package, therefore not applicable" was the comfortable and
  WRONG inference. `linter/_project_type.py` gates `project-type` to drive a
  category-severity FLIP (io/path warning→error for research); it scopes
  SEVERITY, not APPLICABILITY. The rules are meant to run everywhere. The
  notice now says so, and says the verdict covers nothing about them.

  This notice printed accurately on every affected run for eleven days and
  nobody acted. A present, correct, unactioned disclosure is not fixed by
  making it louder; it is fixed by making it decidable.

## [0.44.0] - 2026-08-10

**A release in two halves, joined by one idea: refuse to answer when you
cannot.** The store learns to reject writes it cannot justify — an entitlement
fence on the oplog, a compare-and-set that can no longer be opted out of by
accident, and two guards that catch a store configured to lose its data. On the
other side, three more checks stop reporting "fine" for runs in which they
measured nothing. That was 0.41.0's theme as well, and the recurrence is the
point: an exit code, a log classifier and an empty API answer each looked like
their own small bug, and all three were the same mistake.

### Added

- **The oplog FENCE — "was this writer still entitled?" (#538, #539).**
  `Store.put` takes a three-valued `expected_revision`: `NEW_RECORD`, an int,
  or `ANY_REVISION`. The third is the opt-out, it had ZERO production call
  sites, and nothing enforced that. `store/README.md` told the reader to run
  `rg ANY_REVISION` to audit it by hand, which makes the guarantee depend on
  someone remembering to look. It is now a test that fails, shipped with the
  additive migration the fence needs. This is sequencing for ADR-0006
  Decision 7, which opens TCP 55432 to external clients: a lock nobody can
  bypass has to exist *before* there are clients who could bypass it.

- **`kind` accepts the INTENT spellings `daemon` / `periodic` (#542).** The
  three existing kinds mixed two axes. `service` names an intent and already
  spans two mechanisms (a systemd unit, or the respawn loop used where
  `systemd --user` is absent), while `timer` and `cron` are the *same* intent
  with the scheduler welded into the type name. The new spellings normalise on
  the way in, with no provider changes, so nothing has to migrate to benefit.

### Performance

- **Bulk store writes share one transaction — ~8.7x (#541).** Both dialects
  connect in autocommit, which is right for a single interactive write and
  wrong for bulk work: one logical op costs three statements (oplog insert,
  row upsert, cursor advance) and therefore three commits. Adopting the real
  3,712-card board took 87.7s, which is what surfaced it. Measured at both
  scales because they could have had opposite signs — 3,712-op adoption
  18.59 → 2.06 ms/op (9.0x), and 60 replays of 5 ops 8.99 → 1.04 ms/op
  (8.65x).

### Fixed

- **`ci verify` reported "the pull request is NOT ready to merge" when it had
  simply not been able to run.** `EXIT_NOT_READY` was `2`, and **Click exits 2
  on a usage error** — before any of our code runs. So an installed
  scitex-dev predating the `ci verify` subcommand answered
  `No such command 'verify'` with exit 2, and the gating hook rendered that
  as a confident verdict about a pull request that was green on 7/7 checks.

  Exit codes are now `0` ready / `10` not ready / `11` cannot determine,
  leaving `1` and `2` to the framework. The collision is enforced by
  `assert_no_domain_code_is_framework_reserved()`, which runs **at import**
  in every process that imports the module — including the subprocess a
  gating hook shells out to.

  The constitution already forbade this in as many words (§2), and the rule
  was walked past by someone who had read it, inside the change that fixed
  two sibling instances of the same defect. That is why the check executes
  rather than advises: a rule that must be remembered is forgotten exactly
  when it matters.

  `EXIT_USAGE` was also declared as `1`, which was wrong — Click uses `2`.
  Mislabelling someone else's exit code is how `2` came to look free.

- **A dead attempt counted forever, so no re-run could ever clear it.** One
  head commit can carry several runs of a check name — a manual re-run, or a
  push and the pull request opened from it. Every row counted, so an attempt
  that died from infrastructure poisoned the verdict permanently. A verifier
  that cannot be un-failed by a successful re-run is broken precisely where
  re-runs exist.

  Only the most recently **created** attempt per name decides readiness, which
  is what branch protection uses. **Created, not started:** a queued run can
  start later than a run created after it, and ordering by start time
  produced a green verdict on a pull request GitHub was holding at
  `BLOCKED`. Superseded attempts are still reported, never dropped, so an
  intermittent check stays visible instead of being laundered into a pass by
  one lucky retry.

- **The verdict printed a SHA that the merge command rejects.** `render()`
  abbreviated the head, and `--match-head-commit` refuses anything but the
  full 40 characters, so the documented two-step handed the reader a value
  the second step would not accept. The pin is the whole safety mechanism,
  and a pin that errors is a pin people stop passing. The verdict now prints
  the full head and emits the ready-to-run pinned merge command.

- **The audit gate could pass on an error it did not know how to read.** The
  skip-rules classifier only examined lines whose payload began with `[`.
  Anything else was dropped into neither bucket, so it could never appear in
  `non_skipped` — and the guard `if skipped and not non_skipped` then masked
  the entire failure.

  The lines taking that path are the ones that matter most: the auditor
  reporting that it could not **run**. Measured in the field — scitex-hub's
  CI has carried `Error: No module named 'requests'` since 2026-08-05,
  plainly visible in the job log and invisible to this classifier for four
  days, while the gate reported success.

  Error-tier unbracketed lines now count. They can never be masked, and that
  is correct by construction rather than policy: masking is keyed on rule id
  and these lines carry none, so no `skip_rules` entry can ever match one.
  An auditor that could not run must not be silenceable.

  The level check is a whitelist (`ERRO`/`ERROR`/`FAIL`/`FAILED`/`FATAL`/
  `CRIT`/`CRITICAL`). The inverse test would promote any unrecognised
  `word:` prefix to an error, reddening builds on `note:` or `usage:`.

### Changed

- `ci/_mergeable.py` split into `_exit_codes`, `_check_run`, `_readiness` and
  `_gh`, with `_mergeable` remaining the orchestrator. **No public name
  moves.** The exit-code vocabulary is what a hook or release script needs
  *without* `subprocess` and the GitHub decision tree, and that coupling is
  part of why the collision above sat unread at the top of a large module.

### ⚠️ Upgrade note — read this if your gate declares `MAX_MASKED_VIOLATIONS`

This release can turn a green gate red, and **the obvious remedy is a trap
for a specific set of packages.** Which one you are decides what to do:

**If your audit gate has NO masked-violation ceiling** — this is the common
case; twelve of thirteen scitex repositories are here — then a new error may
appear saying the auditor could not run. Install the missing dependency. The
audit then runs, its findings appear as ordinary gradeable output, and you
are done. Nothing below applies to you.

**If your gate declares `MAX_MASKED_VIOLATIONS`**, installing the dependency
may surface a backlog your gate has never graded, because the auditor that
would have found it was silently disabled. Expect a **count**, not a
one-line fix. Measured on scitex-hub: 102 findings appeared, every one
already in their `skip_rules` — so all were masked, but masked still counts
against the ceiling, taking it from 151 to roughly 253.

**Do not resolve that by raising the ceiling.** A ratchet that may only
decrease is load-bearing; raising it converts a visible red into a silent
breach, which is the same defect wearing a different number. The workable
path is to measure first and then pay down:

    # what would appear, by rule
    grep -oE '\[§[0-9a-b]+\]' <audit-output> | sort | uniq -c | sort -rn

    # then check whether one message dominates — if so it is one
    # conversion applied N times, landable group by group, and each
    # group lands the ceiling DOWN rather than up

On hub, 95 of the 102 were the same `§4b` message, which turned "a
migration campaign" into a single repeatable change. Your ratio may differ;
the method does not.

## [0.43.1] - 2026-08-09

**The audit gate stops reading a "could not measure" notice as a violation
of the code.** If you are on 0.38.1 and blocked by PS-169 or PS-224, come
straight here rather than to 0.43.0 — see the upgrade note below.

### Fixed

- **`testing.audit_all_for_package` counted warn-tier NOTICES as violations.**
  The classifier stripped the level word (`ERRO: ` / `WARN: `) only to *reach*
  the rule bracket and then never read it, so a notice and a finding were
  indistinguishable. Because the mask guard is `if skipped and not
  non_skipped`, a SINGLE unmatched notice discarded an entire skip-rule mask
  and failed a green tree.

  Measured by scitex-hub on the real failing run: 205 violation lines
  classified, 151 masked, **1 non-skipped** — the `[§10w] COULD NOT MEASURE
  RELIABLY … No verdict` line, alone.

  That is UNKNOWN collapsed into the failure pole. `§10`, `§10w`, `TALLY` and
  `defer` now never count as violations, and severity is read rather than
  discarded.

  `NON_ATTRIBUTABLE_RULES` in `_cli/audit/_diff.py` already knew these lines
  describe the machine rather than the diff; this consumer simply never
  consulted it.

- **`[defer]` — the same defect, reported 2026-07-21 and fixed at the source
  this time.** It had been worked around downstream by adding `"defer"` to a
  package's `skip_rules`, with the comment *"remove when scitex-dev excludes
  notice lines from classification"*. The workaround held, so the defect
  survived nineteen days and returned as `§10w`. Masking a could-not-measure
  notice suppresses the one signal saying the measurement is untrustworthy,
  so consumers should NOT carry these in `skip_rules`.

### Upgrade note — if you are pinned below 0.43.0

Do not use 0.43.0 as an intermediate step. The two pins are broken in
opposite ways:

| | 0.38.1 | 0.43.0 | 0.43.1 |
|---|---|---|---|
| PS-169 on a new hosted line | ratchets W→**E** | flat W | flat W |
| PS-224 on `ubuntu-latest` | **rejects** | accepts | accepts |
| §10w notice in the gate | — | **fails a clean tree** | reported, not fatal |

Jump straight to 0.43.1.

### Known, not fixed here

The **§10 import-budget threshold** itself. In-SIF measurement (scitex-hpc)
shows a first-launch penalty that exceeds the fixed 100ms bound on every
interpreter — cold 136/168/193ms against warm 43-50ms — and that the cost is
the *containerised interpreter*, not the node: same machine, host python
cold 39ms / warm 18ms versus SIF cold 193ms / warm 46ms. A bound sampled
once, on a freshly started container, will trip on any host running a SIF.
That is a threshold-design question and gets its own change.

An earlier reading attributed this to CI-node load; that was **refuted** by
control measurement (loaded node 18ms, idle node 21ms) and is recorded as
refuted rather than dropped.

## [0.43.0] - 2026-08-05

**A release that stops two rules from blocking the work they were meant to
protect, and gives the host registry a way to be corrected.**

The CI-runner rules were written under a "never use GitHub-hosted runners"
mandate. The operator superseded that on 2026-08-05 — Spartan comes out of CI,
hosted runners are a permitted fallback — and the rules had not caught up. Two
of them were failing compliant work.

### Fixed

- **PS-169 no longer blocks the migration it exists to inform (#512).** The
  rule shipped at `W` but escalated any violation NEW relative to the git
  baseline to `E`. Under the new directive that is inverted: a repo running on
  `ubuntu-latest` for months stayed at `W` (permitted), while a repo MOVING a
  job off Spartan introduced a new violation and got blocked. Measured on
  scitex-hub's PR #561, where it fired at `[E]` and blocked a PR whose fix
  commit was titled "run the pack publish on the self-hosted pool". Every PR
  in this migration is new-violation-shaped by definition.

  The ratchet is removed, with no promote-to-`E` path left behind. Detection is
  unchanged — hosted usage is still reported, because "why is this repo's CI
  slow?" is a real question — but it is advisory and never fails a build. The
  message, rule text and slug all said "forbidden without exception"; a rule
  reporting at `W` while its text forbids teaches the reader the opposite of
  what the gate does. `ci.yml.tmpl` carried the same claim and renders into
  every repo, so a re-apply would have re-asserted the retired policy over a
  per-repo fix.

- **PS-224 accepts GitHub-provided destinations (#492, first shipped here).**
  It landed on `develop` after `v0.42.0` was cut, so every repo installing
  scitex-dev unpinned kept getting the old behaviour. Consequence measured by
  scitex-hpc: their nightly `release-ci` failed four consecutive nights
  (08-01..08-04), all four from this one rule — 14 violations, every one a
  bare `[ubuntu-latest]`.

  GitHub serves its own images, so such a job cannot exhibit the failure
  PS-224 exists to catch: a destination no machine serves is not rejected, it
  is QUEUED FOREVER. Those jobs were flagged only as a side effect of the
  "unserved" arithmetic — harmless while hosted runners were forbidden, a false
  positive at `E` the moment they were permitted. Self-hosted destinations are
  still checked, at `E`, with no ratchet.

- **PS-215 described a failure that cannot happen.** It told readers "a user
  who runs this exact command gets a resolver error". `pip` does not refuse an
  undeclared extra — it warns and EXITS 0 with the base package installed. The
  docstring distinguished a loud case from a quiet one, and there is no loud
  case: both exit 0. The user sees the remedy SUCCEED, hits the original
  failure again, and has no reason to connect them. That is what makes the rule
  worth having — not that the remedy errors, but that it cannot.

### Added

- **`HostRecord.aliases` — re-key a host without orphaning the old name
  (#514).** Host names are on-disk KEYS (cron entries, JobSpecs, sync configs,
  other packages' registry rows, card scopes); rewriting one silently orphans
  every reference, and the orphan renders as "nothing to do" rather than as an
  error.

  The motivating case: the fleet's NAS numbering is GENERATIONAL — `nas-01` /
  `nas-02` / `nas-03` ascend as machines are REPLACED — and the bare name `nas`
  follows whatever is current. It is a MOVING ALIAS: when a `nas-04` arrives,
  every config keyed on it addresses different hardware, with nothing logged.
  A moving alias belongs in `aliases`, never in `name` — it is a way to REACH
  a host, not a way to IDENTIFY one.

  Canonical keys resolve first and exhaustively, so an alias can never capture
  another host's canonical name. An alias claimed by two hosts raises rather
  than picking one. Malformed alias lists fail loudly instead of degrading to
  empty, since a silently-empty list is exactly the orphan this prevents.

- **The host registry refuses an ambiguous write (#513).**
  `get_hosts_yaml_path` resolves through `Path.home()`, which inside an agent
  container is `/home/agent` — so a write from a container landed in a private
  copy no host-side reader opens, and every layer reported success. Measured:
  `sac host add` did this, and `sac host validate` then reported "ok, 2
  peer(s)" about the shadow.

  It survived because the two files are byte-identical — every CONTENT check
  agrees, and only IDENTITY distinguishes them. Rather than detecting
  containers (which needs a reliable signal and a hardcoded username, both of
  which rot), the write path counts visible registries and REFUSES when more
  than one exists. Reads are unchanged: a reader answering with what it can see
  is defensible, a writer guessing is not.

  Consequence, stated plainly because it is intended: no containerized agent
  can write the registry by the default path. The refusal names the route —
  run it on the bare host, where only one registry is visible and the same rule
  permits it.

## [0.42.0] - 2026-08-04

**A release about saying which thing you mean.** Every entry is a place where
something was inferred — a scope, an owner, a location — and the fix was to make
the caller state it, so that forgetting fails loudly instead of resolving to
whatever was nearest.

### Added
- **The scope and identity contract every SciTeX app conforms to (#499).**
  `scitex_dev.scope` ships five frozen dataclasses — `Principal`, `Project`,
  `Member`, `Scope`, `AppSpec` — that Django, Gitea, the CLI and every leaf
  conform to, rather than each restating. Authority is decided by who ENFORCES,
  not who stores: Gitea owns repo/visibility/human-ACL because it is what blocks
  a `git clone`; scitex-dev owns the shape and the agent-as-principal concept
  because nothing else defines them; anything in Django is a projection.

  Agents are first-class principals, with one rule doing the work of three:
  `effective_role(agent) = min(granted, owner's role on the same project)`. An
  agent can be revoked alone; creating one gains nothing, so agents are not a
  privilege-escalation path; and revoking the OWNER revokes their agents,
  because the ceiling drops with them — no cascade to remember, no orphaned
  agent still holding access after the person is gone.

  `AppSpec` carries TWO independent axes, `data_lives_at` and `view`. Collapsing
  them cannot express two of the five shipped apps: a Scholar library is not
  rebuilt per manuscript, and Storage files belong to a person while projects
  refer to them.

- **The leaf-facing credential primitive (#500).** `resolve(name, ctx=...)` is
  what a leaf calls at runtime, and `register_secret_group(dev, pkg=...)` gives
  any leaf the SAME `dev secret` CLI — the same code, not a copy, because a copy
  is what drifts and drift in a convention is invisible until someone counts
  adoption and concludes the convention never existed.

  The store is the SSOT; the environment is the injection channel, since a
  container or CI job has no private key. **The environment is consulted only
  for owner-less contexts**, and that limit is load-bearing: `os.environ` is
  process-wide while a Django worker serves many users from one process, so
  honouring an env override for a per-user secret would hand user A's value to
  user B's request and look like a successful lookup on both.

- **`<pkg> dev` — the canonical §13 self-maintenance group (#495).** scitex-dev
  now obeys the rule it ships. `cron`, `hooks` and `skills` moved under `dev`;
  the `scitex_dev.jobs` aggregators moved under `ecosystem dev`. Every old
  spelling keeps working through a Phase W warn-forward alias.

### Changed
- **`SecretContext.scope` has no default (#501).** Every caller states which
  scope it means; forgetting is a `TypeError` at the call site. The previous
  default was the empty `Scope()` — safe in that it never guessed a user, but it
  still let the most dangerous call construct successfully: a request handler
  that forgot to pass the requesting user got a valid object pointed at the
  standalone store, read real data, and returned. `Scope.standalone()` and
  `Scope.everything()` are named constructors so the no-owner cases read as
  declarations rather than as omissions; neither looks the current user up.

### Fixed
- **A group alias swallowed `--help` (#495).** Click's help option fires during
  PARSING, so `scitex-dev skills self-explain --help` printed the alias's own
  two-line help and dropped `self-explain` with no error, while the same command
  WITHOUT `--help` forwarded correctly. Discovery through the old name — exactly
  what a user reaches for after a rename — was the only broken part.
- **§1a and §13 could not both be satisfied (#495).** §1a required `skills` at
  top level; §13 requires it under `dev`. scitex-dev, which owns both rules, was
  the first package caught in the fork and every adopter reaches it next. §1a now
  accepts either location, preferring `dev`; a Phase W alias still does not
  satisfy it, because an alias forwards and does not host the verbs.
- **Two builders registered a `dev` group on main (#495).** Click's
  `add_command` is a dict assignment, so the later silently replaced the earlier
  and everything mounted on it: `dev` held `secret` alone, with cron/hooks/skills
  gone and no error anywhere.
- **A latent `AttributeError` on the credential failure path (#500).**
  `SecretUnavailable` interpolated `ctx.pkg`, a field that stopped existing at a
  rename. It sat on the failure path, so it would have replaced a clear "secret
  not found" with a crash the first time a secret was genuinely missing.

### Testing
- Three tests asserted on `CliRunner.result.output`, which MIXES stderr, while
  invoking commands that now warn there via a Phase W alias. They passed locally
  and failed on every CI leg. The local green depended on test ORDER plus a
  leftover marker file under `${XDG_RUNTIME_DIR:-/tmp}` suppressing a
  once-per-session warning — so re-running locally reinforced the illusion. They
  now read `.stdout`, the stream the contract actually names. 34 more instances
  of the same shape remain across the suite, latent until something writes to
  stderr on their path.

## [0.41.0] - 2026-07-31

**A release about checks that could not tell "passed" from "never ran".** Nearly
every entry below is the same defect wearing different clothes: a gate reported a
clean verdict for a run in which it measured nothing, and nobody could see the
difference from the outside. One of them was blocking merges across the whole
ecosystem.

### Fixed
- **The net-new key embedded the checkout name, blocking merges repo-wide (#485).**
  `_ABS_PATH_RE` matches slash-TERMINATED segments, so `/home/x/proj/pkg/src/a.py`
  collapses to `a.py` — correct for a FILE path, where keeping the stable basename
  is what stops two different files keying as one. A DIRECTORY subject has no
  trailing slash, so the regex left its last component, and that component is the
  checkout NAME, which differs between HEAD and the staged baseline worktree by
  construction:

  ```
  ERRO: <dist> (/home/x/.worktrees/floor):    project-structure: 14 error(s)
  ERRO: <dist> (/home/x/.worktrees/base-abc): project-structure: 14 error(s)
  ```

  Same finding, same counts, two identities — one phantom net-new plus one phantom
  disappearance on every PR emitting such a line. Measured on scitex-cards
  2026-07-31: 95 keys each side, 1 new, 1 gone. `audit` is a REQUIRED check, so
  three correct PRs sat unmergeable behind a finding that did not exist.

  The fix reuses what the caller already had: `_audit_all_new_only` computes
  `roots` and passed it to `unparsed_finding_lines` — the raw-TEXT half of the
  diff — but not to `extract_violation_keys`, the KEY half. One half was
  checkout-independent and the other was not; that asymmetry was the defect.
  Widening the regex was rejected: it would also eat the stable basename of file
  paths and collapse distinct findings, which is the collision `_unparsed_key`
  exists to avoid.

  The existing `test_same_finding_under_a_different_checkout_root_keys_identically`
  passed throughout, because it varies the path PREFIX — exactly what the regex
  strips correctly. It exercised the working half and never the failing one.

- **§10 not running looked identical to §10 passing (#480).** The gate had three
  bare `return`s where it never measured anything — no console-script entry point,
  an entry point yielding no top-level module name, and a failed measurement
  subprocess. Each returned without appending a finding, which is precisely what a
  package measuring comfortably under budget does.

- **§10 timing findings were attributed to a diff.** A timing measurement describes
  the repo AND the machine at that instant; net-new keying claims it describes the
  change. Those are different objects, so §10 findings are no longer attributable.

- **The masking summary hid what it could not read (#471).** `classify_output` did
  a bare `continue` on any line `is_violation_line` rejected, so the summary was
  computed over a silently narrowed set. It could print "0 unmasked error(s)" while
  the run exited non-zero — the exit code comes from the sub-auditors' return codes
  while the count came from whatever survived the filter.

- **PS-224 advised relocating attacker-triggerable secret jobs (#475).** The
  guidance moved jobs onto the credential box, which is the wrong direction for a
  job an attacker can trigger.

- **`--version` answered confidently when resolution was a coin flip.** Version
  resolution is THREE-valued and the CLI collapsed it to two.

### Added
- **Generated gates carry a version marker and assert their anchor (#484).** A
  generated artifact previously had no staleness signal, measured across
  `~/proj/scitex-*/tests/develop/test_audit.py`.

- **A clean CLI verdict states its denominator (#483).** `SUCC: <pkg>: no CLI
  convention violations` read identically whether the walker inspected forty
  commands or zero. A verdict without a denominator cannot be distinguished from a
  run that never happened, and the empty case rendered as the clean case.

### Changed
- **The CLI-convention walker is extracted so it can be edited (#482).**
  `_summary/_audit.py` was 1949 lines against a 512-line write hook, so the hook
  refused every edit to it — blocking four separate pieces of work on the walker.

- **`__version__` is deferred off the import path (#478),** one of two eager
  metadata reads.

### Tests
- **The alias `__name__` check is skipped, not relaxed (#481).** Two
  parametrisations failed because the scitex-todo to scitex-cards compat shim makes
  the import succeed and then `__name__` reports the canonical module.

- **A missing OPTIONAL extra skips rather than fails (#479).** Six tests in
  `test__self_explain.py` failed when the `[skills]` extra was absent. The wrapper
  raising `SystemExit` with an install hint is correct for the CLI path, but in a
  test it renders as six red tests that say nothing about the change under test.

- **The round-trip test is named after the module it exercises (PS-204).**

## [0.40.4] - 2026-07-30

**PS-224's diagnostic text told you something false, and acting on it caused
unnecessary work.** No behaviour change — same jobs flagged, same severity,
same registry. Only the sentence a human reads is corrected.

### Fixed
- **PS-224 claimed GitHub queues an unmatchable job forever (#472).** Verbatim
  from the rule's own output: *"GitHub does not reject an unmatchable job — it
  queues it forever, so this never fails, it just never runs."* False for
  GitHub-**hosted** labels, measured twice independently — `ubuntu-latest` jobs
  start, run and complete in under a minute. This project merged four releases
  on those green checks while its own rule text said they could never run.

  The **finding** was always right: PS-224 validates `runs-on:` against a
  registry of self-hosted destinations, so flagging `ubuntu-latest` is correct
  under a self-hosted-only CI policy. The **reason** collapsed two different
  problems:

  | | |
  |---|---|
  | nothing serves this label | the job never runs, silently |
  | served by a pool we don't pay for | the job runs fine, against policy |

  The text asserted the first while detecting the second — and the wrong reason
  is the *more alarming* one. Acting on it as written, you re-point **working**
  jobs at self-hosted runners believing they had never run: churn that looks
  justified because the diagnostic said so.

  The message now states what it checks, keeps the queues-forever claim scoped
  to self-hosted label sets where it IS true, and tells the reader to confirm a
  job is idle before re-pointing it.

### Added
- **A characterization test pinning which emitted finding shapes the key
  extractor can read (#473).** Five emitters produce three distinct line
  formats; the extractor expects a fourth. All three non-trivial formats fail
  for the same reason — the subject after the rule tag is a path or a command
  path, where a single distribution token is expected. That one mismatch is the
  root under three separate defects fixed this week. The test pins today's
  coverage so that unifying the emitters fails loudly here instead of shifting
  coverage silently, and locks in the invariant that must survive it: **no
  `ERRO` shape may ever go back to contributing nothing to the diff.**

### Known gaps
- The emitters are **not** unified — this release only measures the surface.
  The shared `render_finding` and the per-emitter round-trip coverage it needs
  are still to come.
- A rule's rationale is documentation and drifts like documentation, except it
  arrives wearing the authority of a check that just ran. PS-224 was found by a
  peer measuring the claim; no mechanism prevents the next one.

## [0.40.3] - 2026-07-30

**If you run this test suite from a venv without the `[dev]` extra, it has had
no per-test timeout and said so only in a warning. It now refuses to run.**

### Fixed
- **A declared `pytest` ini setting that nothing implements no longer passes
  silently (#468).** `[tool.pytest.ini_options]` accepts any key; when no
  installed plugin registers it, pytest emits `PytestConfigWarning: Unknown
  config option` and carries on. The setting is inert, and the run is
  indistinguishable from one where it applied.

  `timeout = 300` is the key with the stake. Its own comment promises that a
  hung test "fails loud + names itself in ~5 min instead of wedging the whole
  job until GitHub's 6h ceiling" — but `pytest-timeout` lives in the `[dev]`
  extra, so a venv installed without it runs with **no per-test cap**.
  Measured by scitex-hpc on a live host running this suite:
  `pytest_timeout spec: ABSENT`, third-party plugins empty. Not hypothetical —
  and visibly present, invisibly optional, since 2026-06-16 (#206).

  `pytest_configure` now reads what `pyproject.toml` declares and asks pytest
  whether it knows each key, failing with the key, the missing provider, the
  consequence and the fix. The check is **general, not a `timeout`
  special-case**: any declared-but-unimplemented setting is the same defect
  with a different stake.

  Verified in both directions, because a guard that cannot pass is as broken
  as one that cannot fail — plugin present: unchanged; plugin absent: refuses,
  zero tests run.

### Known gaps
- The guard reads `pyproject.toml` at the pytest **rootdir**. A run whose
  rootdir resolves elsewhere (an installed package, an unusual invocation)
  finds nothing declared and is therefore a no-op — it cannot report a setting
  it never saw. It fails open by design: absent config is not a defect.
- It validates that a declared key is **registered**, not that the plugin
  providing it is a working version. A plugin present but too old to honour
  the setting still passes.

## [0.40.2] - 2026-07-29

**If you rely on the audit gate to block a merge, upgrade. On 0.40.1 and
earlier it could print error lines and still exit 0.**

### Fixed
- **An `ERRO` the key extractor could not parse could not block (#465).**
  `extract_violation_keys` skipped every line `_FINDING_RE` failed to match, so
  those errors produced no violation key, could never be net-new, and could
  never reach the exit code — while `filter_to_net_new_lines` treated the same
  line as framing and printed it. The renderer and the counter disagreed by
  construction, and neither could tell.

  Measured on real `audit-all` output before the fix:

  | distribution | `ERRO` lines printed | violation keys |
  |---|---|---|
  | scitex-io | 33 | **0** |
  | scitex-stats | 1946 | 162 (29 `ERRO` dropped) |

  scitex-io is the whole defect in one row: 33 errors on screen, zero keys,
  nothing can be net-new, exit 0.

  Three real `ERRO` shapes the regex cannot express: no bracketed rule tag at
  all (the shape the module's own docstring has always advertised and the regex
  has never matched); a subject carrying a parenthesised path; and two bracket
  groups followed by a path rather than a distribution.

  The fix is **fail-open, not a wider regex** — a wider regex is how this
  arrived. An `ERRO` line that cannot be keyed becomes an `UNPARSED` key, so it
  enters the diff and can block. `filter_to_net_new_lines` applies the same
  test, or the two would disagree again in the opposite direction: a
  pre-existing unparsed error would print on every run while counting for
  nothing, which reads exactly like the bug being fixed.

  An `UNPARSED` key is deliberately **not** subject to `distribution_filter`:
  its distribution is unreadable, and "I cannot tell whose this is" must not
  collapse into "not theirs".

### Known gaps
- **Fail-open covers `ERRO` only, and that restriction is deliberate.** The
  level prefix is *not* a finding discriminator: multi-line advisory banners
  carry it on every continuation line. A run measured 432 level-prefixed lines
  of which 431 were currency-gate prose and 1 was a finding. Failing open on
  any level would have manufactured ~430 findings and blocked every pull
  request — a gate that cannot pass, exactly as broken as the gate that cannot
  fail. A `§`-format finding emitted at **warning** severity therefore still
  produces no key. Across two real runs no warning-severity finding was
  dropped, but that sample was taken with the currency gate bypassed and covers
  two distributions, so it bounds nothing.
- **An advisory can still impersonate a finding.** Fixing that emitter-side is
  what would let fail-open widen past `ERRO` safely.
- **A summary line now counts.** `ERRO: <dist>: N error(s)` is unparsable and so
  becomes an `UNPARSED` key, meaning a reported net-new count can include a
  summary rather than only individual findings.

## [0.40.1] - 2026-07-29

**Upgrade immediately if you have run `ecosystem install-cross-package-gate` or
`ecosystem install-audit-gate` on 0.40.0 or earlier — they could WRITE INTO A
CHECKOUT YOU DID NOT NAME.**

Reported by scitex-hpc within an hour of 0.40.0. Run from inside their worktree,
`install-cross-package-gate` wrote to a *different* checkout sitting on
`develop`, leaving it modified, and printed the resolved path only **after** the
write. It also computed 3 cross-package imports where that branch had 4 — wrong
tree in, wrong content out.

### Fixed
- **Both `install-*` verbs resolved their target by guessing (#462).** They used
  the ECOSYSTEM `~/proj/<name>` lookup with no `--path`, so a caller could not
  aim them correctly even knowing the hazard. `install-audit-gate` shared the
  identical shape and is the larger hazard: it writes three files, one of which
  **appends a marked block to an existing `tests/conftest.py`** — a wrong-tree
  append there silently changes fixture behaviour for every test in that repo,
  in a file no reader would think to diff.

  Now:
  * **`--path`** on both verbs, same semantics as `audit-all --path`.
  * Resolution is least-speculative-first — `--path` > the cwd's enclosing
    repository (via `git rev-parse --show-toplevel`, so a worktree resolves to
    *itself*) > the registry guess, which **announces itself** when used.
  * **The target must BE the distribution named.** Refuses (exit 2) when the
    tree's own `[project].name` disagrees with the argument, printing
    `requested` / `target` / `tree is`. Also refuses a tree that cannot
    identify itself, rather than writing into it.
  * Target and the computed payload are printed **before** any write, and the
    guard runs **before** `--dry-run`, so it cannot be reached past.

  A wrong read costs a session; a wrong write modifies a repo nobody named,
  possibly on a protected branch. These verbs exist to remediate the wrong-tree
  class and had the defect themselves.

  Had the bad write landed in the reporter's own worktree it would have produced
  a PS-140 gate declaring 3 of 4 imports — and a gate that PASSES while missing
  an import is exactly the failure PS-140 exists to catch. The generator would
  have manufactured the defect its own rule detects.

### Known gaps
- `ecosystem test-remote` also resolves via the same guess and then **rsyncs the
  resolved local tree to a REMOTE host**. Same defect class, blast radius on
  another machine, and no local `git checkout --` can undo it. **Not fixed
  here** — a remote-push verb has different failure semantics and deserves its
  own review. Tracked.
- Everything listed under 0.40.0's Known gaps still stands.

## [0.40.0] - 2026-07-29

**Upgrade if any CI workflow runs `audit-all --new-only`.** On 0.39.0 and
earlier that check could print `ERRO:` lines and still exit 0 — measured on
this repo's own REQUIRED merge gate, which passed a PR carrying two
genuinely-new errors.

### Fixed
- **`--new-only` could print errors and exit 0 (#458, #459).** Measured on
  real audit output: **9 finding-shaped lines produced 1 violation key.**
  `_FINDING_RE` matches only `LEVEL: [TAG] <single-token-dist>: <msg>`, so
  both real ERROR shapes were dropped — `[§2] <pkg> <group> <cmd>: …` (the
  subject is a subcommand path, not a bare dist token) and
  `[E] [PS-2xx …] /path: …` (two bracket groups). Dropped findings never
  reached the diff, and `filter_to_net_new_lines` preserves lines it does not
  recognise as findings, so they were reprinted verbatim **as if they were
  narration**. The tally said zero while the output showed errors, and the
  exit status followed the tally.

  Findings the key parser cannot read are now diffed as **raw text** (with
  both checkout roots normalised, since the baseline runs in a temporary
  worktree). Net-new unreadable ERRORS are printed by name, and the run
  **fails open**: `exit 1` if either the keyed or the unkeyed set is
  non-empty. A finding the filter cannot classify must never be silently
  reclassified as prose.

  The filter still filters — a pre-existing unreadable finding is still not
  net-new, so inherited debt does not start blocking unrelated PRs.

- **`--new-only` subtracted an unknown baseline (#458).** `audit-all` exits 0
  (clean) or 1 (findings); any other status means the baseline run itself
  failed. That was treated as "a baseline with no findings", which suppresses
  everything. It is now refused, and the FULL HEAD audit is reported instead.

- **PS-140's remediation named a script that shipped nowhere (#457).** The
  rule told readers to run `python /tmp/write-integration-tests.py <pkg-dir>`
  — a path in a world-writable directory — hedged with "(or the equivalent
  scitex-dev subcommand)". No such subcommand existed, and the checker's own
  docstring promised to "mirror" the same phantom. Reported by scitex-hpc,
  who hit the remediation, found nothing to run, and hand-edited a file whose
  header says it is auto-generated.

### Added
- **`scitex-dev ecosystem install-cross-package-gate <dist>` (#457)** —
  generates the PS-140 cross-package import gate, with `--force`, `--dry-run`
  and `--yes`. It **imports the auditor's own** `_collect_cross_package_imports`,
  so a freshly generated gate is clean by construction and generator and gate
  cannot drift again. Refuses to write an empty gate: parametrizing over zero
  names reports green over zero assertions.

- **`--new-only` now discloses its denominator (#458)** — resolved baseline
  commit, findings at HEAD vs baseline, keyed vs unkeyed counts, and how many
  were suppressed as pre-existing. It also flags the baseline-equals-HEAD
  signature that indicates a baseline graded the wrong tree. This disclosure
  is what exposed the parser gap above, in one run.

### Changed
- `_cli/audit/_project/_registry.py` (1286 lines) split into `_project/_rules/`
  (#457), and the `--new-only` path extracted to `_cmds/_audit_all_new_only.py`
  (#458). Both are pure moves: 121 rules verified identical on
  `(code, section, message, severity, slug)`, and the corpus ASSEMBLY —
  severity/slug tables, co-located merges, and the final `_patch` — was
  deliberately kept in ONE module because the regression suite pins its
  ordering by reading module source and re-executing it. Every existing
  import path still resolves.

### Known gaps
- The underlying divergence is unfixed: **two emitters, one hand-rolled
  parser.** 0.40.0 makes the gate honest about what it cannot read; it does
  not make it able to read it. A test pins the current gap so widening the
  regex fails loudly rather than silently changing the fallback's coverage.
- `audit-all`'s aggregate summary still does not disclose skipped rule
  categories; the linter's `describe_skips()` has no caller under `_cli/`.

## [0.39.0] - 2026-07-29

Upgrade if you run `scitex-dev audit` / `audit-all` or the research-mode
linter. This release fixes four ways the audit could report a verdict that
did not describe what it measured — a silently-dropped exemption block, a
dictionary read from the wrong tree, a severity floor that never reached
`scripts/`, and a headline that counted warnings as errors. Downstream repos
reported all four against 0.38.1.

Note for CHANGELOG readers: 0.38.0 and 0.38.1 were tagged without CHANGELOG
sections. This entry covers everything merged after the v0.38.1 tag; the
0.38.x gap is not backfilled here.

### Fixed
- **A malformed `audit.exemptions` block now FAILS LOUD instead of silently
  exempting nothing (#446).** `_parse_exemptions` returned empty tuples for
  any non-mapping block, so every exemption an author wrote vanished with no
  output at all. scitex-hub hit this within an hour of v0.38.1 using the list
  form (`- rule: PS-224`) and could only diagnose it by downloading the wheel
  and reading the parser. Every malformed shape — block, per-rule value,
  entry, non-integer line, blank reason — now emits a notice NAMING THE
  RECEIVED TYPE and the likely mistake, and block-level notices reach every
  rule's config-error arm. PS-224 gains the config-error arm its docstring
  already promised.
- **`--path` now reaches audit-cli's dictionary, and the audit prints WHICH
  dict file it read (#448).** audit-cli resolved
  `.scitex/dev/cli-audit-dict.yaml` from `Path.cwd()` regardless of `--path`,
  so `audit-all <pkg> --path <worktree>` graded the pinned tree's SOURCE
  against a DIFFERENT tree's dictionary — while the banner confidently
  announced the pinned tree. Reported by scitex-storage against v0.38.1.
  `surface_dict_source` now names the dict file(s) actually read, and
  `audit_all_for_package(path=None)` warns naming the cwd it is guessing from.
- **Research-mode severity promotion now applies under `scripts/` — previously
  it skipped every file there (#449).** The category-severity floor ran only
  on `SciTeXChecker.get_issues`' script path, and `is_script()` returns False
  for anything under a configured `script_dirs` / `library_dirs` entry, whose
  branch early-returned before promotion. Since a research repo keeps
  essentially all figure code under `scripts/`, the promotion was inert
  exactly where it was meant to bite: paper-scitex-clew measured STX-FM010 /
  FM011 / FM016 / FM019 / P006–P009 at `warning` in the same file where
  FM001 / FM002 / FM003 / FM006 / P003 reported `error`. Both exit paths now
  share one `finalize_issues` step.
- **Findings render at their OWN severity, and the summary reports
  per-severity counts (#454).** `_emit_human` computed one max severity for
  the whole run and printed every violation — and the count noun — at that
  level: on PR #447 a single genuine §10 breach relabelled six standing
  §12/§13 warn-tier findings as `ERRO:` and reported "7 error(s)" for 1 error
  and 6 warnings. The collapse propagated further than cosmetics, because
  `_audit_masking.is_error_line` reads severity off that prefix and fed
  audit-all's "N unmasked error(s)" tally. The headline now reads
  "1 error(s), 6 warning(s)", always printing both bands. The JSON path never
  collapsed severities (it carried none) but gave no way to tell the bands
  apart either; it now emits a per-violation `severity` and a per-record
  `severity_counts`.
- **The §10 import-budget gate now reports "COULD NOT MEASURE RELIABLY"
  instead of a verdict it cannot support (#454).** The escape hatch fired only
  when `baseline > threshold`, so a node with a fast bare interpreter but slow
  cold-cache package I/O sat in the strictly-enforcing regime and blew the
  budget — the verdict was decided by the runner's I/O weather, not the code
  under test (measured minutes apart on the same branch: CI baseline 167ms /
  full 781ms → ERROR; local baseline 1796ms → skipped). Subtracting a baseline
  assumes constant overhead, but a slow-I/O node applies a multiplicative
  slowdown and the package import does strictly more file I/O than bare
  startup. The budget is NOT raised; instead a trust gate runs BEFORE the
  verdict (baseline sanity as a ratio of budget, sample dispersion across all
  N samples, and margin-within-noise). Warn-tier, always printed, always
  counted.
- **Duplicate dist-info: resolution is UNSPECIFIED, not "the older one", and
  the remediation now distinguishes a same-layer duplicate from a read-only
  lower layer (#451, #453).** `importlib.metadata` walks `sys.path` and takes
  the first name match, with no version comparison and no tie-break, so the
  winner is a property of path iteration order — measured on three hosts it
  went both ways. The consequence is unchanged and is the point: the reported
  version may not describe the files that actually run, in EITHER direction.
  The "delete the stale dist-info directory — safe" advice is now scoped to a
  SAME-LAYER duplicate, with the read-only-lower-layer case promoted to a
  distinct CASE 3 (there `rm -rf` only writes a mask in the caller's upper
  layer, so the image still ships two dist-infos and every fresh container
  starts broken — fix the IMAGE). Overlay mechanics are labelled INFERRED, not
  measured. Every command in the remediation was run first against throwaway
  venvs; the prior claim that `--force-reinstall` does not remove a duplicate
  was wrong and is corrected — it removes one per run, so re-check the count.
- **Duplicate counting no longer treats a NAME MATCH as evidence of an install
  (#451).** An entry must BE a directory (an overlayfs whiteout is a
  character-special node) AND contain `METADATA`. A present-but-unreadable
  `METADATA` still counts: absent means residue, unreadable means a corrupt
  install, and collapsing those would let real corruption escape through the
  residue door.
- **PS-224's shipped floor is a UNION with per-host state, never a fallback
  (#445).** Stale or absent per-host state can no longer subtract from the
  floor that ships in the package.

### Added
- **A generated audit gate can no longer be missed by a partial local run
  (#448).** The gate lives at `tests/develop/test_audit.py`, outside the
  directory people naturally run — scitex-storage went CI-red on 4 audit
  errors after a local green, twice. `tests/conftest.py` now carries a marked,
  idempotent guard block: if a session would otherwise report SUCCESS and the
  gate was never seen, the session fails and names the reason. An already-red
  session is left alone. The guard records the gate from
  `pytest_runtest_logreport` as well as collection, so a `-n auto` xdist run —
  where collection happens in the workers and never reaches the controller —
  stays green. Opt out per-run with `SCITEX_DEV_ALLOW_PARTIAL_RUN=1`. Existing
  `tests/conftest.py` files are appended to, not replaced; your own fixtures
  are preserved.

### Removed
- **The inert `[tool.scitex_dev] category` channel is retired (#452).** A
  census of all 68 ecosystem repos (68/68 fetched live) plus 119 local
  repo-root `pyproject.toml` files found ZERO declarations, against a positive
  control of 34 repos carrying the `[tool.scitex_dev]` block at all. PS-165's
  category branch never fired for any repo — every package was audited against
  the `library` baseline regardless — so nothing changes for any consumer.
  Gone: `read_package_category()`, the `_CLI_TOOL_EXTRAS` requirement list and
  its `cli-tool` branch, category interpolation in both PS-165 messages, the
  rule text telling packages to declare the key, and the
  `09_package-categories.md` skill page. UNTOUCHED and unrelated:
  `project-type` in `.scitex/dev/config.yaml` and the ECOSYSTEM registry's own
  `category` field.
- **`clean_stale_dist_info()` is now a deprecated, inert shim (#451).** It
  sorted a package's dist-infos by MTIME and `rmtree`'d all but the newest,
  and the skills-export path called it unconditionally. Mtime is not version
  ordering. MEASURED BEFORE CHANGING ANYTHING, and the measurement lowered the
  severity: the rmtree was UNREACHABLE — a grouping-key bug put every
  distribution in a group of size 1, so nothing was ever deleted. No fleet
  damage occurred and none was possible. It is removed anyway, because the
  obvious one-line fix to that typo would ARM an mtime-ordered rmtree inside
  an unrelated export path. Replaced by the observational
  `find_duplicate_dist_infos()` / `report_duplicate_dist_infos()`, which group
  correctly and therefore see duplicates the predecessor never could.

### Security
- **The CLA workflow now calls the org reusable, SHA-pinned (#447, #450).**
  `.github/workflows/cla.yml` runs on `pull_request_target` and
  `issue_comment` — triggers an unauthenticated stranger can fire on a public
  repo, in BASE-repo context, holding a write token and
  `GH_PERSONAL_ACCESS_TOKEN`. scitex-dev was still calling UPSTREAM
  `contributor-assistant/github-action` at the mutable `@v2.6.1` tag, which
  the action's owner could silently repoint. #450 pinned that tag to its
  resolved SHA as an interim; #447 then deleted the inlined jobs entirely in
  favour of the org reusable (which calls the org-owned fork at a fixed SHA),
  itself pinned to a SHA rather than `@main` so a fleet-wide change cannot
  land unreviewed. The `LLEmacs` owner allowlist entry is carried over
  explicitly — taking the reusable's default would have silently started
  demanding a CLA signature from an already-allowlisted contributor.
  Not addressed: these jobs still run third-party code on persistent shared
  self-hosted runners adjacent to fleet credentials. Tracked separately;
  pinning does not fix it.

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
- **Config-layout: untracked stray machine state (#375).** a stray `.scitex/clew` database file
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
