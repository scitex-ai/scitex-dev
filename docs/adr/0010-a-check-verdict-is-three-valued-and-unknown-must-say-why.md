# ADR-0010 — A check verdict is THREE-valued, and `unknown` must say why

**Status:** Accepted
**Owner:** scitex-dev, as protocol primitive provider
**Spec:** `src/scitex_dev/status/spec/verdicts.yaml` + `schema/{check,report}.schema.json` — language-independent, and the source of truth
**Implementation:** `scitex_dev.status.Verdict` / `Check` / `rollup` (Python), derived from that spec
**Extends:** ADR-0007, which built the same package's other type
**First consumer:** scitex-cards' `health` doctor

## Why this exists

The operator, 2026-08-11, on relocation preflight:

> "I keep feeling that if we just got that STATUS right — and status itself is
> pretty important for making the system stable."
>
> (rendered in English; the original was Japanese, which by standing rule does
> not appear on public surfaces)

Preflight is one instance of "status". The fleet already had a shared shape for
the general case — the `health` doctor's
`{package, ok, checks: [{name, ok, detail, hint}], summary}`, with the rule that
every failing check carries an actionable hint. It is a good shape and it had
one defect.

**`ok` was a boolean.** It had no way to say *I could not find out*.

## The measured cases

- **Nine relocation probes, 2026-08-11.** Refused `http 403` by hosts running a
  daemon too old to have the endpoint. The 403 is a real 403 and it is **not an
  answer to the question asked**, which was "may this agent relocate?". Recorded
  as `not-ok` it grounds nine healthy agents. Recorded as `ok` it moves an agent
  onto a host nobody inspected. Both are false, and a boolean has no third slot.
- **The card-store doctor, same day.** It could not open its own store and
  reported `ok: false` on two checks — `terminal_state_honest` and
  `no_falsely_blocked` — whose questions it never got as far as asking. The
  detail said "cannot read the task store"; the verdict said "this is broken".
- **The card-database identity check.** Two databases reported the same uuid
  with different contents. The only honest answer was `cannot-tell`, and it had
  to be encoded outside the boolean as a special case, because the type had no
  room for it.

Collapsing *unknown* into one of its neighbours is the most common way this
fleet ships a wrong answer. Before this ADR the type **required** it.

## Decision

### 1. Three values, closed, and none is a default

```python
class Verdict(enum.Enum):
    OK = "ok"          # asked, answered, the answer is good
    NOT_OK = "not-ok"  # asked, answered, the answer is bad
    UNKNOWN = "unknown"  # could not find out
```

`unknown` is a **measured outcome**, never a fallback: the checker tried and
could not tell. A checker that has not run yet has no verdict at all, which is
the absence of a check, not this value.

Three and not more. Every richer taxonomy anyone reaches for — degraded,
skipped, timed out, not-applicable — is a **reason** for one of these three, not
a fourth decision, and it belongs in `detail` where free text can carry the
specifics. The decision surface is genuinely ternary because a reader of an
aggregate has exactly three moves: proceed, stop, or go and find out.

An open set would reintroduce the collapse it was meant to fix: a consumer
meeting a member it does not implement has to guess which neighbour it belongs
to, and it will guess. `Verdict.from_wire` refuses an unrecognised value rather
than decaying it, for the same reason ADR-0007 §V1 refuses an unknown `kind`.

### 2. This is NOT the stored `ok` that ADR-0007 §9 forbids

ADR-0007 forbids storing `ok` beside a `StatusCode` because there it is
**derivable** from the code, and two fields that can disagree eventually will.

A verdict is not derivable, and the reason is the whole point of this ADR:
**the same code means different verdicts depending on the question asked.**
`http 403` answering *"am I allowed to do this?"* is a definite `not-ok`. The
same 403 answering *"may this agent relocate?"*, returned by a daemon that has
never heard of the endpoint, is `unknown`. Deriving one from the other is the
collapse, not the cure.

So the two types compose rather than compete: a `Check` carries an optional
`cause: StatusCode`, and the native code survives verbatim exactly as ADR-0007
requires. `http 504` ("I stopped waiting"), `errno ETIMEDOUT`, `process 255`
(ssh transport), `grpc UNKNOWN` and `dns SERVFAIL` are all borrowed, not
re-invented — `kinds.yaml` already notes that gRPC's own `UNKNOWN` is *"the code
for 'the outcome could not be determined'"*.

### 3. `unknown` must carry WHY, enforced at construction — twice

An unknown with no reason is barely better than the boolean it replaced: the
reader still has to guess, and now has a third word for guessing.

The rule is enforced in **two** places because it has two doors:

```python
Check.unknown(name, reason, hint)   # reason and hint are REQUIRED, positional
```

and `__post_init__` refuses a blank or whitespace-only `detail`, so the
dataclass constructor cannot get around it either. This is `FieldPolicy`'s
posture (ADR-0006): the schema raises where it is built rather than trusting
callers. A rule enforced in one place is a rule that holds until someone uses
the other door.

`not-ok` likewise requires a `hint` — the constitution's *"an error that only
states what broke is half-written"* — and `unknown` requires one too, saying
**how to find out**. That is M2's logic one layer up: an unknown that names no
probe leaves the reader to wait and then guess, which is the 30 s / 5 min 12 s
incident exactly.

**Rule C5 — M1 on a check's prose — is GUIDANCE, not a validator rule, and the
difference was measured.** An earlier draft of this ADR enforced `message`'s
no-inferred-cause marker list on `detail` and `hint`. Tried against the first
real consumer it REFUSED a correct check: scitex-cards' `backend_mode` states
that cards are on postgres and the inbox is on yaml, then says writes
"therefore land in different engines" — a deduction from two facts the same
check supplies, in prose recording a dated measurement. The marker list is a
heuristic tuned for SHORT status messages; a check's `detail` is long and
explanatory by design, and the very first one tripped it.

The structural protection is the **verdict**, not a word list. A checker that
could not establish something reports `unknown` and says why, which is a
stronger statement than any phrasing rule because it changes what the reader is
allowed to do next. And a rule that refuses the first honest adopter gets the
whole type bypassed — ADR-0007's own law is that thin gets adopted and thick
gets bypassed.

### 4. Aggregation states its policy, and there is no default

```python
rollup(package, checks, *, unknown_policy)   # keyword-only, required
```

A known failure always wins: any `not-ok` makes the rollup `not-ok` under every
policy. Only when there is no known failure does the policy matter, and then the
right answer depends on what the aggregate is **for**:

| Policy | An unknown makes the rollup | For |
|---|---|---|
| `refuse` | `not-ok` | irreversible action taken on the checks — relocating an agent, promoting a release. Never act on a host you could not inspect. |
| `propagate` | `unknown` | a report something else decides from. "I cannot tell you the whole is healthy" is what actually happened. |
| `tolerate` | `ok`, unknowns named | "may I proceed?" rather than "is everything known?" — a dashboard tile, an advisory banner. |

Baking any one of these into the type makes the other two wrong, so the type
does not choose. **There is no default**, because a default policy is the same
collapse a boolean verdict is, moved one level up and made harder to find —
nobody reads the aggregation function.

The naive aggregate `ok = not any(failed)` is wrong in **both** directions over
a set containing unknowns: it answers "fine" when the truth is "I could not
look", and it offers no way to answer "do not proceed" when the looking is what
failed.

**An unknown is never silent.** Under every policy the summary names every
unknown check. There is exactly one summary implementation and no way to supply
your own, because that is the rule a caller in a hurry would drop.

### 5. The wire form does not change

The verdict travels in the **existing** `ok` field, three-valued as JSON
`true` / `false` / `null`.

This was not a free choice — it is what scitex-cards already does, argued in its
own `_health` docstring: *"the third value rides in `ok` as JSON `null` rather
than in a fifth key sac/cct would not read"*, with tests pinning both the
four-key report and the four-field check record. Adding a `verdict` string
beside `ok` would have made every existing reader wrong about a shape that was
not the problem, and would have created exactly the two-fields-that-can-disagree
hazard ADR-0007 §9 exists to prevent. Both JSON schemas therefore reject a
`verdict` or `status` key outright, as ADR-0007's reject `ok` and `retryable`.

`Verdict.from_ok` refuses truthy stand-ins — `1`, `""`, `0` — because `bool(x)`
is the single line that has eaten the third state everywhere it has been lost.

**What a boolean-only reader sees:** `null`. It is falsy in both Python and
JavaScript, so an unmigrated reader treats an unknown as "not fine" — the safe
direction, and the same direction `refuse` chooses deliberately.

**What is NOT on the wire:** the rollup policy. It is a property of the caller's
decision rather than of the observation, and a fifth key would break the
four-key contract for every reader. A JSON consumer must therefore **not** infer
from a top-level `ok: true` that every check was answered; `summary` is where
the unknowns are visible, and they are named there under every policy.

## Consequences

**The fleet already had four of these, each in its own corner.**
`scitex_dev.versioning.Currency` (FRESH/STALE/UNKNOWN, with an aggregation
property whose precedence is documented), `scitex_dev.store.StoreStatus`
(RECOGNISED/FOREIGN/UNREADABLE), `scitex_dev.testing._audit_outcome`
(PASS/FAIL/UNKNOWN, where "UNKNOWN is a FAILING verdict" — a `refuse` policy in
the wild), `scitex_dev.hygiene.Landed` (`bool | None`), and
`scitex_dev._cli._doctor`'s `Status = Literal["ok", "fail", "skip"]`. The idea
was never missing. What was missing is that the SHARED shape — the one leaves
publish and agents read — was still a boolean, and each of those five is
unreadable to the others. This ADR does not migrate them; convergence is
per-consumer and incremental, exactly as ADR-0007's boundary declarations are.

**`_cli._doctor`'s third value is `skip`, not `unknown`, and they are different
questions.** "There was nothing to check here" is not "I could not check". That
one deserves the distinction before it is migrated, not a rename.

**Adoption is per-consumer.** Nothing has to be agreed ecosystem-wide before the
first caller ships. A doctor migrates by building `Check` objects instead of
dicts and calling `rollup` with its policy stated; its JSON does not move.

**A leaf consuming this takes a runtime dependency on scitex-dev**, as ADR-0006
already established for `scitex_dev.store` — *"leaves consume the primitive,
they do not re-implement it to a documented spec."* `scitex_dev.status` imports
the standard library and `yaml`, and nothing else in scitex-dev, so the import
cost is the packaging edge and not the module. That edge is a real decision for
each leaf and is called out in the PR that makes it, not assumed here.

## Deliberately not here

Recorded so the next reader does not helpfully add them back.

- **No fourth verdict.** Not `degraded`, `skipped`, `timed-out` or
  `not-applicable`. Each is a reason for one of the three; put it in `detail`.
  If a case arrives where a reader must genuinely take a **fourth action**, that
  reopens this line — but it should arrive as a measured case, not a prediction.
  The nearest real candidate is `_cli._doctor`'s `skip`, above.
- **No `verdict` / `status` key on the wire.** §5.
- **No `unknown_policy` on the wire.** §5.
- **No default rollup policy.** §4. This is the one that will be proposed again,
  usually as "surely `tolerate` is the obvious default"; it is the default that
  hid the bug this ADR exists to fix.
- **No severity, no weighting, no `confidence` float.** A verdict is what a
  reader branches on. Anything finer belongs in `detail`, which is free text and
  can carry it without asking every consumer to agree first.

## Related

- ADR-0007 — the other type in this package, and the borrow-don't-invent rule
  this one follows for `cause`
- ADR-0006 — the "leaves consume the primitive" pattern, and `FieldPolicy`'s
  raise-at-construction posture
- `src/scitex_dev/status/spec/verdicts.yaml` — the normative source
- scitex-agent-container PR #956 — the M1 message shape C5 applies to checks
