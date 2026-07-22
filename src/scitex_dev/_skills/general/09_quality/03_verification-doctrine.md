---
description: |
  [TOPIC] Verification Doctrine — how a check fails without going red
  [DETAILS] Rules for trusting your own measurements, organised by claim type: absence claims need a positive control, causal claims need one varied variable and a hunted counter-example, content claims need a second independent reader, artifact claims need the artifact actually in use. Includes the six-state search-failure taxonomy, the vacuous- and inert-control rules, and the status words (`skipped`, `masked`, `0`) that fuse a failed measurement into a clean one. Use before reporting a zero, a green, or a root cause.
tags: [scitex-general-quality-verification-doctrine]
---

# Verification Doctrine

Every failure recorded here is one shape:

> **A failed measurement rendered as a confident value.**

The instances differ only in which layer swallowed the error — the tool, the
shell, the report format, the peer who relayed it. The output is always
well-formed, plausible, and wrong; nothing goes red.

Measured ratio (2026-07-22, five agents): of that day's verification failures,
**every one** was caught by a person deliberately re-running a check a
different way. **None** was caught by the check.

## 0. The six states a search can be in

Name which state your defence addresses, or the defence is decoration.

| # | State | Caught by | Natural symptom |
|---|---|---|---|
| 1 | Did not run | positive control | none — a clean zero |
| 2 | Ran, found nothing | re-run vs known-present string | none |
| 3 | Ran, skipped a category | fixture planted in every category, asserted by **count** | none |
| 4 | Ran, invented matches | known-absent string must return zero | none |
| 5 | Ran, returned **some but not all** | count assertion (60 needles → 60) | none — partial looks complete |
| 6 | Ran, corrupted content | byte-for-byte vs independent reader | none — plausible and wrong |

Rows 3 and 5 are invisible to the defences for 1, 2, 4 and 6, and vice versa.
Row 5 is nearest to undetectable: the count is the only tell.

## 1. Absence claims → positive control

*Claim: "X does not exist / there are no Y."*

Run the same enumeration, on the same root, against something **known to
exist**. If the control returns nothing, the enumeration did not run and no
absence conclusion is licensed.

**Empty output is not a negative result.** Measured cases:

- `rg` served by GNU grep, erroring out, returning zero.
- A `tsc` invocation that never executed; the grep for `error TS` over the
  failure text honestly returned zero.
- `crontab -l | grep -i sac` → "no restarter scheduled". The entry invokes
  `bin/auth-heal.py` — no `sac` substring. The filter *could not* have matched.
- `grep … | head -30` truncated a search into apparent absence; the finding was
  below the cut. Same shape twice in one hour: 8 real audit ERRORs sat below a
  47-warning block in both incidents.
- Tag pattern `refs/tags/[0-9]+\.` matched nothing because tags are
  `v`-prefixed. 160 tags read as zero.
- `fd … 2>/dev/null` returned empty because the binary was absent. The
  suppressed stderr made *missing tool* indistinguishable from *no matches*.
- `rg --no-filename "^ *model:" DIR/ 2>/dev/null` → zero lines over 102 files
  that match. Under grep, a directory arg without `-r` matches nothing, and
  `2>/dev/null` discarded "Is a directory".
- Container `~` is `/home/agent`, not the operator's home; a `~`-relative check
  of an operator path returned zero against a 107-entry directory.

TELL: any zero or empty you are about to reason from.
CHECK: a positive control **in the same invocation** — search for something you
know is there. Never suppress stderr on a probe whose result you will use.

Naming the enumeration is necessary but not sufficient: it can be a different
program than the one named, silently scoped by a file nobody mentioned
(`.gitignore`), or read from the wrong side of a mount.

## 2. Causal claims, which-knob → vary exactly one variable

*Claim: "X is what causes Y."*

Instance: a probe varied a flag *and* a pattern, attributed the difference to
the flag, and sent a peer a false confirmation of their root cause. It was the
pattern — an anchored regex against an indented line.

A two-variable probe cannot license a one-variable conclusion. Sending one to a
peer is worse than keeping it: it reads as independent confirmation and
corrupts their conclusion too.

## 3. Causal claims at all → hunt the counter-example

*Claim: "the mechanism is Z."*

Instance: a "deterministic 10/10" that was true of ten runs sharing one pattern
and one ordering, and false the moment either varied.

"I did not see one" is not "I looked for one."

**Advocacy is the tell.** Three over-claims in one session, all while arguing a
case: "fleet-wide" from one instance; "fd is unreliable" from an untested
example; "-h is the root cause" from an under-varied sweep. Conceding already
triggers scrutiny; advocating does not. When you notice you are advocating,
re-measure the number you are leaning on.

## 4. Content claims → second independent reader

*Claim: "the file says / the output shows …"*

Instance: a search tool silently replaced everything before the first colon of
a matched line with `0`. `MARK AAA:BBB:CCC` → `1:0:BBB:CCC`.

**A positive control proves the search RAN, not that its output is INTACT.**
The control string is still found while the surrounding content is destroyed.
Rules 1–3 protect against false *absence*; this failure produces non-zero,
plausible, wrong results.

For anything you will quote or act on, read the file, or use a second reader of
a different kind. Instance: a count claim was re-run through `git grep` (git's
own matcher, not GNU grep) and agreed. One engine's count never addressed it.

Related tell: nonsense output gets normalised — `1 matches in 0 files:` is
internally contradictory and was read as clean anyway.

## 5. Artifact claims → verify the artifact in use

*Claim: "the config/binary/tree says …"*

Ask the tool which artifact it resolves (`--show-config`,
`python -c "import X; print(X.__file__)"`) before reading a path you already
believe in. The tell is identical every time: *you reach for the artifact by
absolute path, because that is how you inspect a file you already believe in.*

- A config compared byte-for-byte between two agents that **neither agent's
  tool reads**; the real configuration was compiled-in defaults.
- A `--version` that lied while an editable install served an abandoned tree.
- A fix whose content was verified but whose binary never ran.
- `.venv/bin/python` listed fine under `ls -la` — symlink chain intact — and
  failed only at exec, because the target `/usr/bin/python3.11` did not exist.
- **A release is not done at the tag.** PS-220's `W` default had to be read out
  of the downloaded wheel: the tag is what setuptools-scm reads, while
  consumers install from PyPI.

## 6. Peer claims → corroboration must be independent in kind

Instance: scitex-dev quoted sac's own error string back to sac; sac raised its
confidence *because it came from a peer*. Two agents appearing to agree was one
source quoted twice.

When a peer relays something, ask where they got it before counting it as a
second source.

## 7. Controls that license nothing

**Vacuous — the control cannot fail.** Run the known-bad case in the same
batch. If it passes too, throw the result away. Instance: 20/20 for two
workarounds *and* 20/20 for the known-broken form — one sentence away from
"workarounds verified", when what was observed was a run in which nothing could
fail.

**Inert — the control exists but is disarmed.** More dangerous than a missing
one: a missing guard gets built, a present-but-inert one closes the ticket and
is then cited as coverage. One day's instances: a CI recovery path behind an
unset variable; a reconciler installed-but-disabled against an enabled preset;
a health gate that read *absence* as green; a lint rule shipped at a severity
its own exit code ignored; a cleaner scoped to a directory the bloat was not
in, printing `removed=0 kept=235` — the same output a clean tree produces.
Never accept "there is a check for that" — ask when it last fired and what it
did.

**Layer-blind — the probe runs below the effect.** A probe at layer N+1 cannot
observe an effect at layer N, and reports *the absence of the phenomenon*
rather than its own blindness. Instance: an engagement qualifier inside a shell
script, where the effect operates on the tool-call layer above it; it reported
NOT-ENGAGED on a container where an inline call demonstrably engaged.

**Sampling — the unit of variation is the Bash call.** Identical command text
gave one result 5/5 in one invocation and the opposite 20/20 in another, each
internally consistent. Every loop inside one call is **one** sample, not N.

## 8. Fixing a masking bug: arm both arms

A fix for "the cron reports 0 when it cannot read" can be satisfied by
relabelling every case UNKNOWN — green, and the true-zero signal destroyed. The
control arm — *readable and genuinely empty STILL reports zero* — is what
distinguishes the repair from the relabel. Mutation-prove both arms.

## 9. Status words that fuse a failed measurement into a clean one

- **Skipped is not passed.** A CI summary read "8 passed" where one leg was
  `skipping`. Report the skipped state as its own state; never fold it into a
  pass count.
- **Green can be declared masking.** An audit went green partly because 150
  violations were masked by declared `skip_rules` (PS-139, PS-221) — visible in
  the log, but `audit: SUCCESS` alone reads as clean. Distinguish *fixed* from
  *deferred-with-a-declaration*.
- A count that includes what it did not check is not a count.

## 10. Commissioned findings land as cards, not prose

A commissioned finding is the easiest kind to shelve: it arrives as a **report**,
not a **symptom**. A symptom interrupts you; a report waits. Measured:
scitex-dev's own agent reported the cron read defect hours before a peer nearly
escalated a false fleet outage on it. This needs a mechanism, not resolve —
commissioned findings go into scitex-cards as cards, not a session transcript.
