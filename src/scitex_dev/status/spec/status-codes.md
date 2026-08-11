# SciTeX Status Protocol — specification

**spec_version:** `1`
**Owner:** scitex-dev, as protocol primitive provider
**Normative artefacts:** `kinds.yaml`, `scitex-codes.yaml`, `boundaries.yaml`, `schema/*.json`
**Governing decision:** ADR-0007

This document is **language-independent and is the source of truth.** The
Python package `scitex_dev.status` is a DERIVED implementation, in the same
sense that `scitex_dev.store` is the one implementation of ADR-0006: leaves
consume the primitive, they do not re-implement it to a documented spec.

When this document and an implementation disagree, this document is right.
That is enforced, not asserted — `tests/scitex_dev/status/test__spec.py`
parses these files and fails when the Python drifts.

MUST / MUST NOT / SHOULD / MAY are RFC 2119.

---

## 1. The type

```python
@dataclass(frozen=True)
class StatusCode:
    kind: str          # "http" | "process" | "grpc" | "dns" | "errno" | "scitex"
    code: int | str    # the NATIVE code within that kind, verbatim
    message: str       # a HINT: what I am doing, and how you verify it
```

Three fields. The thinness is the feature.

`kind` is a **discriminated-union tag**: it tells the reader *how to read
`code`*, and nothing more.

```python
StatusCode(kind="http",    code=503,           message=...)
StatusCode(kind="process", code=137,           message=...)
StatusCode(kind="grpc",    code="UNAVAILABLE", message=...)
StatusCode(kind="dns",     code="NXDOMAIN",    message=...)
StatusCode(kind="errno",   code="ECONNREFUSED", message=...)
```

### 1.1 There is NO SciTeX translation

`kind="http", code=503` means a **real HTTP 503**. `kind="process", code=137`
means a **real exit 137**. The native code is preserved verbatim, always.

This is the central decision, and it is a reversal of an earlier draft that
built a fifteen-word canonical SciTeX vocabulary with mapping tables into
HTTP, gRPC and POSIX. That design was **lossy**: mapping `process 137` onto a
canonical `RESOURCE_EXHAUSTED` or `INTERNAL` destroys the fact that it was
**SIGKILL**, and "the process was killed" is usually the only thing worth
knowing. `dns/NXDOMAIN` loses the same way — folded into a canonical
`NOT_FOUND` it stops being distinguishable from `SERVFAIL`, which has a
completely different fix.

A design that discards the native code in order to gain a shared word has paid
too much for the word.

It is also **adoptable**, which the vocabulary was not. A three-field dataclass
gets used. A vocabulary that requires ecosystem-wide agreement before anyone
can ship gets discussed, and then bypassed.

### 1.2 Why `kind` is called `kind`

`protocol` is wrong the moment `process` and `errno` are in the set — neither
is a protocol. `domain` invites the question "which domain?". `type` collides
with a Python builtin and reads as a value's data type rather than as a
namespace tag. **`kind` reads correctly to someone who has never read this
spec**, which is the test that matters.

For the same reason the class is `StatusCode`, not `SciTeXStatusCode`. It is a
container for **other people's** status systems.

## 2. Each boundary declares the kind it borrows

There is no universal vocabulary to agree on. Each call site makes a
**documented choice**, recorded in `boundaries.yaml`. That file is normative;
the table below is an index of it, and a conformance test checks that every
declaration in it borrows a registered kind.

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

A boundary may borrow **any** kind. `grpc/CANCELLED` over a Unix socket is
legal and is preferable to minting a SciTeX code, because the `kind` tag
travels with the value and says which dictionary to open.

A boundary absent from `boundaries.yaml` has not declared yet. That is a gap
to close, not licence to improvise.

## 3. `message` — a hint, and an assignment of work

> 「message は「こちらは○○をします。でもあなたが動作を確認しなくてはなりません
> よ」という意味です」
> 「message はヒントであり、エージェントが誤解しないようにします。すなわち、
> 確認の手段、問い合わせの手段を hint で与えればよいのです」
> — the operator, 2026-08-11

`message` does two jobs, and both are load-bearing:

**(a) It declares what the SENDER is doing or will do.**
**(b) It tells the RECEIVER that verification is THEIRS, and hands over the
means** — how to check, how to ask.

It SHOULD therefore answer three questions:

| | |
|---|---|
| **What to DO** | "retry in 10s", "fix the PATH", "nothing" |
| **What the sender IS doing** | "phase=container_creation since 06:15:08Z" |
| **How to ASK** | a runnable probe: `` `sac agents list <name>` `` |

```python
StatusCode(
    kind="http", code=202,
    message="accepted as xch_20260811T061508Z_scitex-compute-04_a1b2c3; "
            "phase=container_creation since 06:15:08Z; "
            "retry in 10s or poll `sac agents list claude-code-telegrammer`",
)
```

This is why there is **no `retryable` field**. For an agent reading the
result, *"retry in 10s and here is how to check"* is strictly more useful than
a boolean — and retryability is already readable from the code within the
declared kind (`503` yes, `403` no).

### 3.1 This makes the handshake rule mechanical

The constitutional rule is *"confirm arrival, not dispatch; A→B without an
observed B→A is not a handshake, it is a hope."* Clause (b) is that rule
turned into a field: the sender's own message states that confirmation is
still owed and names the instrument.

**Measured, 2026-08-11:** scitex-dev sent an a2a message to scitex-cards, got
back no error worth acting on, and treated **sending as delivery**. Nothing in
the return told the sender that confirmation was still outstanding. A message
obeying clause (b) says so in the sender's own words.

The same shape is what left five operator DMs undelivered on 2026-07-29: an
enqueue reported success and delivery never happened. **Enqueued and delivered
are different facts and need different statements.**

### 3.2 M1 — the NO-INFERRED-CAUSE rule (normative)

> **A message states what was MEASURED and what to DO NEXT. It never names a
> cause it did not observe.**

Stating an *observed* cause is fine (`ENOENT: /etc/foo`). *Concluding* an
unobserved one is forbidden. Hints inform; they do not conclude — a hint that
asserts a cause has stopped being a hint and become a verdict the reader did
not ask for and cannot check.

**Measured, 2026-08-11:** a transport-failure message printed **"THEREFORE the
fault is specific to `POST /agents`"** on the strength of two control probes
that cannot see that route. A reader acted on it **within two minutes** and
filed a P1 against the wrong component. The route was fine: the client had
stopped listening after 30 s while the server worked the request for
**5 min 12 s**. Fixed in scitex-agent-container PR #956.

The validator rejects markers that assert an inference — `therefore`,
`this means`, `the fault is`, `root cause`, `must be caused by`, `proves
that`. Words that report an observation (`because`, `due to`) are deliberately
**not** on that list.

The prescribed shape, taken from PR #956:

```
OBSERVED: <what was actually measured>
RULED OUT: <what the measurement eliminates>
NOT ESTABLISHED: <what it does NOT settle, and why>
NEXT, to find out rather than guess: <the probe to run>
```

"Ruled out a daemon-wide fault" is a claim the evidence supports. "Therefore
this route is faulty" is not, because **a route still working past the timeout
is indistinguishable, from outside, from a wedged one.**

### 3.3 M2 — a non-final code MUST say how to ask

When a code's native meaning is *"received, not finished"* (`http 102`,
`http 202`), `message` MUST name a way to ask — a backtick-quoted command, a
URL, or a path. Without one the reader can only wait and then guess, which is
the 30 s / 5 min 12 s incident exactly.

## 4. The immediate ack, and its separation from completion

> 「A -> B というやり取りがあって、B -> A と即座にステータスを返す」
> — the operator, 2026-08-11

**Every A→B is answered by B→A immediately.** The ack is prompt and is
**separate from completion**.

```
A ──── request ─────────────▶ B
A ◀─── 202 + exchange id ──── B     immediately. "I have it. Here is the handle."
                              B     ...works...
A ──── ask (by id) ─────────▶ B     whenever A wants to know
A ◀─── 200 / 500 / ... ────── B     the completion, as a separate fact
```

- `202 Accepted` is the shape for **"received, still working"**. It is a real
  HTTP 202 — B genuinely accepted the request.
- The ack MUST carry the **exchange id** (§5).
- A caller MUST NOT read an ack as a completion, and MUST NOT read the absence
  of a completion as a failure.
- **A client-side timeout is `http 504`** — *"I stopped waiting."* That is
  already the honest sentence, which is why no SciTeX code was invented for
  it. `504` is a statement about the CALLER's patience; it says nothing about
  what B did, and the message MUST send the reader to the exchange id instead.

**Measured, 2026-08-11:** a spawn client's deadline elapsed at **30 s** and it
reported a peer failure. The server had accepted the request and worked it for
**5 min 12 s**, getting a long way through before failing for an unrelated
reason. With an immediate 202 and an id, A has a fact ("accepted, id X") and a
handle, instead of a guess.

## 5. The exchange id

> 「A -> B という通信が起こるたびに id を発行すればよいのでは？」
> — the operator, 2026-08-11

**Every exchange gets an id.** It is what makes §4 work: without one, "poll for
status" has nothing to point at, and a timed-out caller can only guess.

- **Issued** by B on receipt, once per exchange.
- **Returned immediately**, in the ack, before any work is done.
- **Quoted** by A in every follow-up question about that exchange.
- **Stable and quotable across hosts.** An agent on compute-04 asking the
  laptop about an exchange uses the same string, so the id carries its origin
  and its time rather than depending on local context.

Format (normative):

```
xch_<YYYYMMDD>T<HHMMSS>Z_<origin-host>_<6 hex>
xch_20260811T061508Z_scitex-compute-04_a1b2c3
```

Time-ordered when sorted as text, attributable to the host that issued it,
unique without coordination. `message` on a 202 SHOULD carry the id and say
how to query it (M2).

## 6. The ledger

> 「~/.scitex/scitex.db に通信の製本としてまとめられる気がします」
> 「毎回同じ datatype なので、見ればよいだけ」
> — the operator, 2026-08-11

Every exchange yields the **same shape**, so they all go in **one table**, and
"what happened to request X" becomes a **lookup instead of an investigation.**

### 6.1 Storage is `scitex_dev.store` — not a hand-rolled file

Normative: the ledger is a record kind in **`scitex_dev.store`** (ADR-0006).
This spec does not re-decide storage and MUST NOT be read as licence to open a
path.

That buys, for free: one store per host, oplog-based **directed replay**
between hosts, HLC ordering, field-level merge, and no delete verb. It matters
concretely — the fleet is consolidating onto compute-04 and exchanges span
both hosts, so an exchange opened on the laptop must be answerable from
compute-04. ADR-0006 Decision 6 also forbids exactly the shortcut this section
would otherwise invite: *"anything deriving a filesystem location from the
store target is the defect, not a workaround for it."*

### 6.2 The record

| Field | Merge | Meaning |
|---|---|---|
| `exchange_id` | IMMUTABLE | identity (§5) |
| `initiator` | IMMUTABLE | A — `host/service` |
| `responder` | IMMUTABLE | B — `host/service` |
| `operation` | IMMUTABLE | e.g. `agent.spawn` |
| `opened_at` | IMMUTABLE | when B issued the id |
| `kind` | LAST_WRITER_WINS | latest `StatusCode.kind` |
| `code` | LAST_WRITER_WINS | latest `StatusCode.code` |
| `message` | LAST_WRITER_WINS | latest `StatusCode.message` |
| `updated_at` | MAX | latest status time |
| `final` | LAST_WRITER_WINS | is the latest status terminal? (`202` is not) |

The identity fields are `IMMUTABLE` because an exchange's participants cannot
change; the status fields are last-writer-wins because a row is the exchange's
**current** state. Its **history** is not lost — the store keeps an oplog and
never deletes, so the ack and the completion are both still readable.

`final` is the one field worth pausing on: it is what makes an unanswered
exchange **findable**. `final = false` and an old `updated_at` is the query
that finds work that was accepted and never concluded — the state that was
invisible on 2026-08-11 and had to be reconstructed by hand.

## 7. Validation — at CONSTRUCTION, and it raises

> 「あなたたちなら通信で使われるコードとか全部知っているでしょ？だから
> dataclass と validator に落とし込めると思うんです」
> — the operator, 2026-08-11

A malformed `StatusCode` MUST fail **where it is built**, not three layers
downstream where the context that would explain it is gone. The validator
raises; it never warns.

| # | Rule |
|---|---|
| V1 | `kind` is one of the registered kinds. An unknown kind is REFUSED, never defaulted. |
| V2 | `code`'s TYPE matches the kind's `code_type` (`http`/`process` int; `grpc`/`dns`/`errno`/`scitex` str). |
| V3 | `code` is in the kind's domain — enumerated where an enumeration exists. `http 999` is refused; a range check alone would accept it. |
| V4 | `errno` codes are NAMES, never numbers. errno numbers are platform-specific: the same integer is a different error on another OS, so a number crossing a host boundary changes meaning in transit. |
| V5 | `scitex` codes are in `scitex-codes.yaml`'s closed enumeration. |
| V6 | `message` is non-empty. |
| V7 | `message` contains no inferred-cause marker (M1, §3.2). |
| V8 | For a code marked `requires_probe` (`http 102`, `http 202`), `message` names a probe — a backtick-quoted command, a URL, or a path (M2, §3.3). |

Per-kind domains are sourced from `kinds.yaml`, so the Python tables are
derived rather than authored. `errno` names come from the platform's own
`errno` table rather than a hand-typed list, because a hand-typed list of a
hundred names is a list with a typo in it.

### 7.1 Reserved: `process` 1 and 2

`process/1` and `process/2` MUST NOT be given a SciTeX meaning. They already
mean "generic failure" and "usage error" in every CLI framework — and argparse
and click both exit **2 for an unknown subcommand**, so overloading 2 lets a
**missing or renamed verb impersonate a real value**.

**Measured in this fleet:** a `may-stop` verb absent from an older install
exited 2. That was indistinguishable from a usage error, and a Stop hook
**failed open** on it.

Read a received 2 as *"this verb may not exist in this install"*, never as a
verdict on the operation you asked for. `126` (found, not executable) and
`127` (not found by the shell) are the same trap one layer down: they report
the SHELL's lookup, not the program's absence.

## 8. What is deliberately NOT here

Recorded so the next reader does not helpfully add it back:

- **No canonical SciTeX status enum.** §1.1.
- **No translation layer / mapping targets.** `kinds.yaml` documents each
  kind's NATIVE meanings so a reader can interpret a borrowed code. It is
  documentation, not a conversion table, and nothing converts.
- **No `retryable` field.** §3. Readable from the code within the kind, and
  `message` says the useful version.
- **No stored `ok` field.** Derive it (`kind == "http" and 200 <= code < 300`,
  `kind == "process" and code == 0`, ...). Two fields that can disagree will
  eventually disagree, and then a reader has to guess which to trust. An
  implementation MAY expose a derived accessor; it MUST NOT serialise one.
- **No large error taxonomy.** `scitex-codes.yaml` has an admission test
  precisely so it stays short.

Thin gets adopted. Thick gets bypassed.

## 9. Versioning

- `spec_version` is a string, currently `"1"`.
- A reader that does not implement a version MUST refuse rather than
  best-effort parse it: partially understanding a protocol message is how a
  field's absence gets read as a value.
- **Compatible within a version:** registering a new kind, adding codes to a
  kind's enumeration, adding a boundary declaration, tightening a message.
- **Requires a new version:** removing a kind, removing a code, changing what
  a kind's `code` field holds, or making an optional rule mandatory.
- `scitex` codes and boundary declarations are APPEND-ONLY. A retired entry is
  marked `deprecated:` with a successor and never deleted — logs outlive code.

## 10. Conformance

An implementation conforms when:

1. It exposes `StatusCode(kind, code, message)` with those three fields and no
   others, frozen.
2. It validates at construction and RAISES on every rule in §7.
3. It preserves the native `code` verbatim and performs no translation.
4. It refuses an unknown `kind` and an unknown `spec_version` rather than
   coercing either.
5. It never serialises a derived `ok`.
6. It issues, returns and records exchange ids per §5, and stores the ledger
   in `scitex_dev.store` per §6.

The reference implementation is `scitex_dev.status` (Python), derived from
these files and tested against them.

<!-- EOF -->
