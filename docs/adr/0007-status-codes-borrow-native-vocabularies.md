# ADR-0007 — Status codes BORROW native vocabularies; SciTeX does not invent one

**Status:** Accepted (operator ruling, 2026-08-11)
**Owner:** scitex-dev, as protocol primitive provider
**Spec:** `src/scitex_dev/status/spec/` — language-independent, and the source of truth
**Implementation:** `scitex_dev.status` (Python), derived from that spec
**Consumers next:** scitex-agent-container, scitex-cards
**Authored by:** scitex-agent-container (sac). scitex-dev's own agent is stopped
for a fleet migration, so authorship of its ADR fell to a peer.

## Why this exists

SciTeX moves work across localhost, LAN, WireGuard, SSH, HTTP, WebSocket,
gRPC, Unix sockets, message queues, AWS, Spartan HPC, other labs' machines and
SciTeX compute. Every one of those layers already says what happened in its own
words — ICMP unreachable, TCP RST, `NXDOMAIN`, HTTP 503, gRPC `UNAVAILABLE`,
SSH disconnect reasons, POSIX exit codes.

The operator's framing, which is the whole motivation:

> "Building a protocol is extremely important. Not just 0/1/none — we have to
> standardise, for SciTeX, the kind of status codes used in communications."
>
> "This should be written up as a spec in scitex-dev and then implemented
> across every communication path. Spec, dataclass and validator should fit
> together."
>
> "scitex-dev holds the primitive and other packages reuse it — that is what
> makes it SSoT and robust."
>
> — the operator, 2026-08-11 (rendered in English; the original was Japanese,
>   which by standing rule does not appear on public surfaces)

That last sentence puts this ADR in ADR-0006's shape deliberately: **leaves
consume the primitive, they do not re-implement it to a documented spec.**

## Decision

### 1. The type is three fields, and it BORROWS

```python
@dataclass(frozen=True)
class StatusCode:
    kind: str          # "http" | "process" | "grpc" | "dns" | "errno" | "scitex"
    code: int | str    # the NATIVE code within that kind, verbatim
    message: str       # a hint: what I am doing, and how you verify it
```

`kind` is a **discriminated-union tag**. It says HOW TO READ `code`, and
nothing more.

```
StatusCode(kind="http",    code=503,           message=...)   # a real HTTP 503
StatusCode(kind="process", code=137,           message=...)   # a real SIGKILL exit
StatusCode(kind="grpc",    code="UNAVAILABLE", message=...)
StatusCode(kind="dns",     code="NXDOMAIN",    message=...)
```

**There is no SciTeX translation and nothing to translate to.** The native code
is preserved verbatim, always.

### 2. This REVERSES an earlier draft of this ADR, and the reason is the design

That draft defined fifteen canonical SciTeX statuses (`OK`, `UNAVAILABLE`,
`DEADLINE_EXCEEDED`, `NOT_RESOLVABLE`, …) with mapping tables into HTTP, gRPC
and POSIX exit codes. It was well-formed and it was wrong. Two reasons, and
they are recorded because the same idea will be proposed again.

**It was LOSSY.** Mapping `process 137` onto a canonical `RESOURCE_EXHAUSTED`
or `INTERNAL` destroys the fact that it was **SIGKILL** — and "the process was
killed" is usually the only thing worth knowing. `dns/NXDOMAIN` loses the same
way: folded into a canonical `NOT_FOUND` it stops being distinguishable from
`SERVFAIL`, which is a completely different problem with a completely
different fix. **A design that discards the native code to gain a shared word
has paid too much for the word.**

**It was not ADOPTABLE.** A three-field dataclass gets used. A vocabulary
requiring ecosystem-wide agreement before anyone can ship gets discussed, and
then bypassed — and a protocol nobody uses protects nothing. The operator's
instinct throughout was that thin gets adopted and thick gets bypassed; the
lossiness argument says he was also right on the merits.

**What the borrowed design gets for free.** The earlier draft had to *invent*
`NOT_FOUND` / `UNREACHABLE` / `NOT_RESOLVABLE` as three separate canonical
statuses, because collapsing them had produced a wrong report. With native
codes preserved, `dns/NXDOMAIN`, `errno/ENOENT` and `errno/ECONNREFUSED` are
**already distinct by construction**. The distinction was never something we
needed to create; it was something the canonical layer was about to destroy.

### 3. `kind`, not `protocol` / `domain` / `type`

`protocol` is wrong the moment `process` and `errno` are in the set — neither
is a protocol. `domain` invites "which domain?". `type` collides with a Python
builtin and reads as a value's data type. **`kind` reads correctly to someone
who has never read the spec**, which is the test that matters.

The class is `StatusCode`, not `SciTeXStatusCode`, for the same reason: it is a
container for **other people's** status systems.

The Python package is `scitex_dev.status`, not `scitex_dev.protocol` — the
identical argument applies to the module name, and a package called `protocol`
holding `process` and `errno` would mislead every reader of an import line.

### 4. Each BOUNDARY declares which kind it borrows

> "For sac too, decide per place which one to use — here we borrow the http
> type, here we borrow process."
> — the operator, 2026-08-11

Not one universal vocabulary. A **documented choice per boundary**, recorded in
`spec/boundaries.yaml` — which is normative; the table below indexes it:

| Boundary | Borrows |
|---|---|
| `sac listen: POST /agents` | `http` (ack `202`) |
| `sac listen: POST /v1/host_exec` | `http` for the route, `process` for the command |
| `sac agents start / stop / restart` | `process` |
| `sac host probe` (multi-hop ssh) | `process` |
| a2a sidecar send / reply | `http` (ack `202`) |
| agent binary / verb resolution | `scitex` (`NOT_RESOLVABLE`) |
| registry lookup of a non-running agent | `scitex` (`AGENT_UNAVAILABLE`) |
| scitex-cards board HTTP API | `http` |
| scitex-cards store put w/ `expected_revision` | `http` (`409`) |
| scitex-cards notification delivery | `http` (ack `202`) |
| `scitex_dev.store` open / read / write | `errno` |
| host / peer name resolution | `dns` |

**That table is the entire coordination cost of this design.** A boundary may
borrow any kind — `grpc/CANCELLED` over a Unix socket is legal, because the
tag travels with the value and says which dictionary to open.

`host_exec` is the case worth reading twice: the ROUTE is `http` and the
COMMAND's outcome is `process`. Two boundaries, two kinds. Folding them is how
an exit 127 gets reported as an HTTP 200.

### 5. `message` is a HINT that assigns verification to the receiver

> "`message` means: *I am doing X — but YOU have to confirm it works.*"
> "`message` is a hint, so that agents do not misunderstand. Give them the
> means to check and the means to ask."
> — the operator, 2026-08-11

It does two jobs: it **declares what the sender is doing**, and it **tells the
receiver that verification is theirs and hands over the instrument.** It should
answer what to DO, what the sender IS doing, and HOW TO ASK.

```python
StatusCode(
    kind="http", code=202,
    message="accepted as xch_20260811T061508Z_scitex-compute-04_a1b2c3; "
            "phase=container_creation since 06:15:08Z; "
            "retry in 10s or poll `sac agents list web-01`",
)
```

This makes the constitutional rule — *"confirm arrival, not dispatch; A→B
without an observed B→A is not a handshake, it is a hope"* — **mechanical**.
Measured 2026-08-11: scitex-dev sent an a2a message to scitex-cards, got back
no error worth acting on, and treated **sending as delivery**. Nothing told the
sender that confirmation was still owed. It is the same shape that left five
operator DMs undelivered on 2026-07-29: enqueue reported success and delivery
never happened.

**This is also why there is no `retryable` field.** For an agent, "retry in 10s
and here is how to check" is strictly more useful than a boolean — and
retryability is already readable from the code within the declared kind.

### 6. M1 — a message NEVER asserts a cause it did not observe

> **A message states what was MEASURED and what to DO NEXT.**

Stating an *observed* cause is fine (`ENOENT: /etc/foo`). *Concluding* an
unobserved one is refused. Hints inform; they do not conclude.

**Measured, 2026-08-11:** a transport-failure message printed **"THEREFORE the
fault is specific to `POST /agents`"** on the strength of two control probes
that cannot see that route. A reader acted on it **within two minutes** and
filed a P1 against the wrong component. The route was fine: the client had
stopped listening after 30 s while the server worked the request for
**5 min 12 s**. Fixed in scitex-agent-container PR #956, whose message shape is
now the prescribed one:

```
OBSERVED: <what was actually measured>
RULED OUT: <what the measurement eliminates>
NOT ESTABLISHED: <what it does NOT settle, and why>
NEXT, to find out rather than guess: <the probe to run>
```

"Ruled out a daemon-wide fault" is a claim the evidence supports. "Therefore
this route is faulty" is not — **a route still working past the timeout is
indistinguishable, from outside, from a wedged one.**

The validator rejects inference markers (`therefore`, `this means`, `the fault
is`, `root cause`, `must be caused by`, `proves that`) and deliberately does
NOT reject observation words (`because`, `due to`).

### 7. A→B is answered by B→A IMMEDIATELY, and every exchange gets an ID

> "There is an A → B exchange, and B → A returns a status immediately."
> "Why not issue an id every time an A → B communication happens?"
> — the operator, 2026-08-11

```
A ──── request ─────────────▶ B
A ◀─── 202 + exchange id ──── B     immediately
                              B     ...works...
A ──── ask (by id) ─────────▶ B
A ◀─── 200 / 500 / ... ────── B     completion, as a SEPARATE fact
```

`202 Accepted` is the shape for "received, still working", and the id is what
makes "poll for status" point at something.

```
xch_<YYYYMMDD>T<HHMMSS>Z_<origin-host>_<6 hex>
xch_20260811T061508Z_scitex-compute-04_a1b2c3
```

Time-ordered as text, attributable to the issuing host, unique without
coordination. The origin is IN the string because an agent on compute-04 asking
the laptop about an exchange must quote the same value.

**A client-side timeout is `http 504` — "I stopped waiting."** That is already
the honest sentence, which is why no SciTeX code was invented for it, and it
says nothing about what B did. This is correction C4 in its final form: the
30 s / 5 min 12 s divergence is not a case for a new status word, it is a case
for an ack, an id, and a message that sends the reader to them.

### 8. The ledger is ONE table, and it lives in `scitex_dev.store`

> "It feels like these could be bound together in `~/.scitex/scitex.db` as a
> record of communications."
> "It is the same datatype every time, so you just look."
> — the operator, 2026-08-11

Every exchange yields the same shape, so **"what happened to request X" becomes
a lookup rather than an investigation.**

**Storage is `scitex_dev.store` (ADR-0006), not a hand-rolled SQLite file.**
This ADR does not re-decide storage. Consuming the primitive buys per-host
storage, oplog **directed replay** between hosts, HLC ordering, field-level
merge and no delete verb — and the fleet is consolidating onto compute-04, so
an exchange opened on the laptop must be answerable from compute-04. ADR-0006
Decision 6 already forbids the shortcut this section would otherwise invite:
*"anything deriving a filesystem location from the store target is the defect,
not a workaround for it."*

Identity fields (`exchange_id`, `initiator`, `responder`, `operation`,
`opened_at`) are `IMMUTABLE`; status fields (`kind`, `code`, `message`,
`final`) are last-writer-wins over the CURRENT state, with history preserved by
the oplog.

**`final` is the field that earns its column.** `final = false` with an old
`updated_at` is the query for work that was **accepted and never concluded** —
the state that was invisible on 2026-08-11 and had to be reconstructed by hand.
It is DERIVED from the status code by the single function that writes the row,
never supplied by a caller, so it cannot come to disagree with the code beside
it.

### 9. `ok` is DERIVED and MUST NOT be stored

`ok` is a read-only property (`http` 2xx, `process` 0, `grpc` `OK`, `dns`
`NOERROR`) and is never serialised. Both JSON schemas reject the key outright,
as they reject `retryable`.

Two fields that can disagree **will** disagree, and then a reader has to guess
which to trust. ADR-0006 records what that costs at scale: a DM committed to
one store while its notification went to another, the write reported success,
and nobody was woken.

`ok` and `final` are also **different questions**, and the type keeps them
apart. `http 202` is `ok` — the request really was accepted — and is NOT
`final`, because the work it accepted has not finished. Reading "accepted" as
"done", and reading "not done yet" as "failed", are the twin halves of the same
missing distinction, and 2026-08-11 produced the second one.

### 10. The validator enumerates the real codes, per kind, and RAISES

> "You all know every code used in communications, right? So it should be
> possible to put them into a dataclass and a validator."
> — the operator, 2026-08-11

| Rule | |
|---|---|
| V1 | `kind` is registered. Unknown kind → REFUSED, never defaulted. |
| V2 | `code`'s TYPE matches the kind (`http`/`process` int; the rest str). |
| V3 | `code` is in the kind's enumerated domain — `http 999` is refused, because a 100-599 range check alone accepts it and a code nobody defined is a typo wearing a uniform. |
| V4 | `errno` carries the NAME, never the number: errno numbers are platform-specific, so a number crossing a host boundary changes meaning in transit. Valid names come from the platform's own table, not a hand-typed list. |
| V5 | `scitex` codes are in a CLOSED enumeration with a written admission test. |
| V6 | `message` is non-empty. |
| V7 | `message` contains no inferred-cause marker (M1). |
| V8 | `http 102` / `http 202` must name a probe in `message` (M2). |

Validation happens in `__post_init__`. **A malformed status must fail where it
is BUILT**, not three layers downstream where the context that would explain it
is gone. The tables are read from the spec YAML, so the Python is derived and a
conformance test fails when it drifts.

### 11. POSIX exit codes 1 and 2 are RESERVED

They already mean "generic failure" and "usage error" in every CLI framework —
and argparse and click both exit **2 for an unknown subcommand**, so
overloading 2 lets a **missing or renamed verb impersonate a real value**.

**Measured in this fleet:** a `may-stop` verb absent from an older install
exited 2. That was indistinguishable from a usage error, and a Stop hook
**failed open** on it.

Read a received 2 as "this verb may not exist in this install". `126` and `127`
are the same trap one layer down: they report the SHELL's lookup, not the
program's absence — which is why `command -v X` missing is `NOT_RESOLVABLE` and
never an absence claim.

### 12. `kind="scitex"` is a closed list, and staying short IS the design

Two members today:

- **`NOT_RESOLVABLE`** — it exists and is reachable, but the name or path used
  does not resolve to it. No native vocabulary has this word: `ENOENT` says the
  path does not exist, `NXDOMAIN` says the name does not exist, `127` is the
  shell reporting its own lookup. None can say *"it is installed and working,
  and this PATH does not see it."*
  **Measured 2026-08-11:** a report stated "compute-04 has no sac CLI" from a
  `command -v` miss plus three guessed paths. sac was installed at
  `~/.env-sac/bin/sac` and working the entire time. "Not installed" sends
  someone to reinstall; "not on this PATH" sends them to fix an environment.
- **`AGENT_UNAVAILABLE`** — an agent is registered and not answering, at a
  boundary where there is **no request** to answer, so there is no response
  code to borrow. (If you are answering an HTTP request, use `503`.)

A code enters this list only when no `http`, `grpc`, `dns`, `errno` or
`process` vocabulary can express it, and the entry must record that reasoning.
A long list means the canonical vocabulary this ADR rejected has grown back
under another name; a conformance test caps it.

## Consequences

**The completeness bar is the boundary table, not the code.** The type is
finished in an afternoon. The work is every boundary declaring what it borrows
— and an undeclared boundary is where an agent improvises, which is the state
this ADR exists to end.

**Adoption is per-boundary and incremental.** Nothing has to be agreed
ecosystem-wide before the first caller ships, which is precisely what the
rejected design would have required.

**The ledger's value is proportional to coverage.** One package writing
exchanges answers questions about that package. The lookup only replaces the
investigation when both ends of an exchange write.

**This must land before the spread.** Every boundary that ships without
declaring a kind is one that has to be revisited, in namespaces scitex-dev does
not own.

**Scope limit, so this is not read as bigger than it is.** The primitive owns
the TYPE, the per-kind validation, the message rules and the ledger's shape.
What any particular code MEANS at a particular boundary stays with the package
that owns the boundary.

## Deliberately not here

Recorded so the next reader does not helpfully add them back: no canonical
SciTeX status enum (§2); no translation layer or mapping targets — the per-kind
documentation describes NATIVE meanings and nothing converts; no `retryable`
field (§5); no stored `ok` (§9); no large error taxonomy (§12).

`FAILED_PRECONDITION`-style additions to the scitex list, and a canonical
retry-classification helper, were both considered and dropped. If a case
appears where a caller genuinely cannot decide from the native code plus the
message, that case reopens this line — but it should arrive as a measured case,
not as a prediction.

## Related

- ADR-0006 — the store primitive this ledger is built on, and the "leaves
  consume the primitive" pattern this ADR follows
- scitex-agent-container PR #956 — the M1 message shape, and the 5 min 12 s
  measurement
- `src/scitex_dev/status/spec/status-codes.md` — the specification itself
