# ADR-0005 — Extras are all-or-nothing; development tooling is a dependency group

- **Status**: Accepted
- **Date**: 2026-08-02
- **Deciders**: operator (directive), scitex-dev (owner), scitex-cards (first consumer)
- **Supersedes**: nothing. **Amends**: the enforcement surface of PS-221.

## Context

On 2026-08-02 the fleet lost its card store. Container definitions pinned
`scitex-cards[mcp]`. That extra does not pull `psycopg`, so every container
came up with a store client that could not reach Postgres.

Three things about that failure matter more than the failure:

1. **`[all]` would have worked.** It includes the `postgres` extra. The
   outage was caused by someone choosing a *subset* — correctly, by their own
   reasoning, from a menu the package offered them.
2. **The wrong pin was documented.** scitex-cards' own fleet-rollout skill
   said `uv pip install -U 'scitex-cards[mcp]>=0.7.1'` — 25 install
   instructions across 17 files prescribed partial extras. Whoever wrote the
   container definitions followed the documentation correctly.
3. **Everyone involved reproduced the failure while diagnosing it.**
   scitex-cards recommended `[mcp,postgres]` — another hand-picked subset —
   an hour after diagnosing the first one, and scitex-dev ratified it on
   image-size grounds. The failure mode is not ignorance; it survives people
   who have just been burned by it.

The operator's position, stated the same morning, is that extras should be
all-or-nothing: the cost of `[all]` is disk and install time, which is small
and recoverable, while the cost of a wrong subset is a silent capability gap
discovered in production, which is neither.

**That position was already shipped policy.** PS-221's own text opens: *"a
PUBLIC install extra must be `[all]` or bare ONLY — with no fine-grained
per-feature menu a user has to assemble by hand."* Both agents debating it
had the rule in front of them and neither read it; scitex-dev argued against
a rule it wrote and enforces.

### Why the existing enforcement did not prevent this

PS-221 requires every public extra to be a *subset of* `all`, so `[all]`
never under-installs. It is correct and it held. It does not — and cannot —
stop someone from pinning a subset instead.

The gap is that PS-221 governs the **package's metadata** and the mistake is
made in a **def file, a workflow, or a README**.

### Why the obvious fixes fail

- **Underscore-prefixed "logical group" extras** (`_mcp`, `_postgres`) —
  proposed, and it is where the operator's memory pointed. It is illegal:
  PEP 508 requires an extra name to begin with a letter or digit, and
  `Requirement("pkg[_mcp]")` raises `InvalidRequirement`. PS-221's docstring
  already records that this advice broke five repositories in 2026-07 before
  being reverted. **The operator was remembering a real event, not
  misremembering a rule.**
- **Making every runtime capability a hard dependency** — proposed by
  scitex-cards. Correct for `psycopg`; wrong in general. `torch` is an
  optional extra in 6 packages, `audio` in 5, `browser` in 3. A rule that
  forces gigabyte ABI-pinned GPU wheels into every install needs an exception
  list, and an exception list is a naming convention wearing different
  clothes.
- **A lint rule banning subset pins outright** — bans a legal construction
  that 30 packages legitimately offer, and enforces at every use site rather
  than at the one definition.

## Decision

### 1. `dev` and `docs` become PEP 735 dependency groups, not extras

```toml
[dependency-groups]
dev  = ["pytest", "pytest-cov", ...]
docs = ["sphinx>=7.0", ...]
```

Development tooling is not a user-facing optional feature. Exposing it
through extras is what forces `all` to choose between two correct rules:
PS-221 says `all` must contain every public extra, and cheapness says `all`
must not contain sphinx. Once `dev`/`docs` are not extras, PS-221 no longer
reaches them and keeps full force over everything it was written for. **No
amendment to PS-221 is required** — a resolution that needs no exception
carved into the enforcing rule is the sign we were looking for.

Verified before adopting:

| check | result |
|---|---|
| PEP 735 adoption today | 0 of 83 packages — greenfield |
| CI installing a *published* sibling's `[dev]` | **0 occurrences** |
| positive control | 265 `pip install` lines across workflows |
| local `.[extra]` installs to convert | 12 |

The zero in row two is load-bearing. Dependency groups are **not** wheel
metadata — they resolve only against a local source tree. Had anything
installed `scitex-X[dev]` from an index, this decision would have been
unimplementable in exactly the way the underscore proposal was.

### 2. `all` references every remaining extra BY NAME

```toml
all = ["mypkg[mcp]", "mypkg[web]", "mypkg[postgres]"]
```

Not by incidental requirement overlap. This matters more than it looks, and
scitex-dev is the proof: its `icons` extra requires `Pillow`, which is absent
from `all`'s own list but present in `all`'s *expansion* because `dev`
happened to require it. PS-221 passes, because closure is checked over
requirements. **Remove `dev` from `all` — which decision 1 requires — and
Pillow silently leaves `[all]`, with `icons` no longer covered and no rule
firing.**

Consequence: decisions 1 and 2 must land **together**, per package. Applying
decision 1 alone can silently narrow `[all]`.

### 3. A public extra with zero requirements is a defect — ALREADY ENFORCED

This is **PS-214**, which already exists and already fires. Measured against
scitex-dev today:

```
check_ps214_empty_extras -> 2 violations
  PS-214 pyproject.toml | `[project.optional-dependencies.cli]` is an empty list
  PS-214 pyproject.toml | `[project.optional-dependencies.cli-audit]` is an empty list
```

`pip install scitex-dev[cli-audit]` installs nothing while reading like it
enables a capability, and that pin appears **33 times** in scitex-dev's own
documentation. No new rule is needed. **The rule was firing the whole time and
nobody saw it**, because the CI gate runs `--new-only` and both violations
predate every baseline. A pre-existing finding is invisible by construction,
which is the grandfathering hazard the constitution warns about
(§2: "a blanket flag also hides every new instance of the same class") applied
to the *reporting* layer rather than the rule layer.

**Action is therefore visibility, not authorship**: a periodic full-corpus
audit whose findings are read, separate from the per-PR `--new-only` gate.

### 4. Documented pins — the gap is PEER packages, not documentation as such

**PS-215 already scans** `.py` and `.md` for `pip install <pkg>[<extra>]` and
flags an extra that does not exist or is empty. It is the right mechanism and
it is built.

Its docstring states one deliberate exclusion:

> Remedies naming a DIFFERENT package (a peer's extra) are intentionally NOT
> checked — verifying a peer's pyproject is out of scope for a cheap,
> single-repo audit pass.

**That exclusion is exactly where the outage lived.** The failing pin was
`scitex-cards[mcp]` written in *sac's* container definitions — a peer pin, in a
`.def` file, on both counts outside PS-215's scope. The scope limit is a real
design constraint (a single-repo pass cannot resolve a peer's pyproject), not
an oversight, so closing it needs the ecosystem-level pass that has the whole
fleet in hand — `scitex-dev ecosystem`, not `audit-project`.

Fleet state, for sizing that pass:

| documented partial pin | occurrences |
|---|---|
| `scitex-dev[cli-audit]` | 33 |
| `scitex-io[h5]` | 12 |
| `scitex-agent-container[mcp]` | 12 |
| `scitex-hub[mcp]` | 6 |

**Flag, never autofix.** scitex-cards' mechanical sweep rewrote a test comment
quoting what a hint *used to say* into "the hint used to say `<the current
value>`", and turned three skip reasons into a claim that is false. A rewrite
keyed on a bare string cannot distinguish an instruction from a description
of one.

### 5. An install check must assert the CAPABILITY, not the import

From sac's post-incident work, and it generalises past this ADR:

> A bare `psycopg/` directory with no `__init__.py` imports as a **namespace
> package**, so `import psycopg` SUCCEEDS and `psycopg.connect` does not
> exist.

So every guard of the form `try: import psycopg / except ImportError:` passes
on a broken image. The partial install did not merely omit a dependency — it
left behind something that satisfies the standard test for the dependency
being present. That is why the symptom surfaced as *"the database does not
exist"* rather than as a missing module.

Build-time and runtime checks must assert the attribute they actually need
(`psycopg.connect`), not that the top-level name imports.

## Rollout

Staged, because a rule that lands as an error on 79 packages gets suppressed
rather than obeyed — which is precisely the outcome scitex-cards refused to
commit when this ADR's own guidance conflicted with a shipped gate.

1. **scitex-dev first.** It is the worst offender on decision 4 (33 pins), it
   ships both empty extras from decision 3, and it demonstrates the decision-2
   trap. An author who fails his own rule hardest cannot ship it to others.
2. Checks land as **warnings**.
3. Per-package conversion as each is touched, not a fleet sweep — decisions 1
   and 2 change `pyproject.toml` and CI in lockstep, which is exactly the bulk
   operation the constitution requires to be staged and dry-run.
4. Warning becomes error once the majority has converted.

## Consequences

- `pip install pkg[all]` becomes true to its name: every user-facing
  capability, and no test or documentation tooling.
- `[all]` becomes the cheapest correct pin, so nobody has a motive to
  hand-pick. **This is the actual mechanism.** The naming convention the
  operator reached for was trying to make the wrong thing untypeable; making
  the right thing cheapest achieves the same end without requiring anyone to
  remember a rule.
- CI installs `--group dev` (pip >= 25.1, uv). 12 call sites.
- Anyone genuinely needing a subset can still pin one. It is legal, it is
  occasionally correct, and it is now a deliberate act rather than the path of
  least resistance.

## Notes on how this decision was reached

Recorded because the process failed the same way four times in one day, and
the pattern is more useful than the decision.

Every rule this ADR reached for **already existed**:

| what was "discovered" | what was already shipped |
|---|---|
| extras should be all-or-nothing | PS-221, first paragraph, verbatim |
| an empty extra is a defect | PS-214, *firing on scitex-dev right now* |
| documented pins should be checked | PS-215 |
| leading-underscore extras are illegal | PS-221's docstring, incl. the five repos it broke in 2026-07 |

Two agents reconstructed each question from first principles and repeatedly
reached the opposite of the shipped answer. The common error was measuring
**practice** — what packages do — and reading non-compliance as evidence that
no rule existed. Non-compliance and non-existence are indistinguishable when
you only count, and the *owning* package being non-conforming reads as the
strongest evidence against the rule.

For a norm, doctrine is the source of truth and the code is the compliance
report. Before proposing an ecosystem rule, grep all three corpora —
`linter/_rules/` (STX-*), `audit/_project/` (PS-*), `_skills/` (doctrine) —
and run the audit against your own repo first.

The one genuinely new thing here is not a rule but a **visibility** finding:
PS-214 has been reporting scitex-dev's two empty extras all along, into a gate
configured to show only what is new.
