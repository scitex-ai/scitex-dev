---
description: |
  [TOPIC] Verification Doctrine — how a check fails without going red, by claim type
  [DETAILS] Rules for trusting your own measurements, organised by what you are claiming: absence needs a positive control, causal needs one varied variable and a hunted counter-example, content needs a second independent reader, artifact claims need the artifact actually in use, peer corroboration must be independent in kind. Includes the six-state search-failure taxonomy. The companion leaf `04_verification-controls.md` covers controls that license nothing, degrade-branch masking, status words, and follow-through. Use before reporting a zero, a green, or a root cause.
tags: [scitex-general-quality-verification-doctrine]
---

# Verification Doctrine — Claim Types

Every failure recorded here is one shape:

> **A failed measurement rendered as a confident value.**

The instances differ only in which layer swallowed the error — tool, shell,
report format, relaying peer. The output is always well-formed, plausible, and
wrong; nothing goes red.

Measured ratio (2026-07-22, five agents): of that day's verification failures,
**every one** was caught by a person deliberately re-running a check a
different way. **None** was caught by the check.

This leaf covers the rule *per claim type*. The controls those rules prescribe
have their own failure modes — vacuous, inert, mispositioned — in
[04_verification-controls.md](04_verification-controls.md), along with masking,
status words, and what happens to a finding after you have it.

## 0. The six states a search can be in

Name which state your defence addresses, or the defence is decoration. None of
the six has a natural symptom — every one looks like a clean result.

| # | State | Caught by |
|---|---|---|
| 1 | Did not run | positive control |
| 2 | Ran, found nothing | re-run vs known-present string |
| 3 | Ran, skipped a category | fixture in every category, asserted by **count** |
| 4 | Ran, invented matches | known-absent string must return zero |
| 5 | Ran, returned **some but not all** | count assertion (60 needles → 60) |
| 6 | Ran, corrupted content | byte-for-byte vs independent reader |

Rows 3 and 5 are invisible to the defences for 1, 2, 4 and 6, and vice versa.
Row 5 is nearest to undetectable: the count is the only tell.

## 1. Absence claims → positive control

*Claim: "X does not exist / there are no Y."*

Run the same enumeration, on the same root, against something **known to
exist**. If the control returns nothing, the enumeration did not run and no
absence conclusion is licensed.

**Empty output is not a negative result.** Measured cases:

- `rg` served by GNU grep, erroring out, returning zero; and a `tsc` that never
  executed, whose failure text honestly contained no `error TS`.
- Three patterns that *could not* have matched what was there: `grep -i sac`
  over a crontab whose entry invokes `bin/auth-heal.py`; `refs/tags/[0-9]+\.`
  over 160 `v`-prefixed tags; a `~`-relative operator path inside a container
  where `~` is `/home/agent` (107 entries read as zero).
- `grep … | head -30` truncated a search into apparent absence. Twice in one
  hour: 8 real audit ERRORs sat below a 47-warning block, below the cut.
- `2>/dev/null` twice turned a broken probe into an empty one: `fd …` with the
  binary absent, and `rg --no-filename "^ *model:" DIR/` over 102 matching
  files (served by grep, where a directory arg without `-r` matches nothing).
  The discarded stderr was the whole diagnosis.
- **Glob filters silently zero a whole tree** (2026-07-23): `rg -l --no-ignore
  '<term>' /home/ywatanabe/proj -g '*.yml' -g '*.yaml' -g '*.sh'` returned **0**
  for a term that was present, while `rg -l 'audit'
  <one-repo>/.github/workflows` found it immediately. Exit 0, no stderr, no
  truncation marker — nothing was suppressed, so the empty result was
  indistinguishable from real absence. The form that worked: loop per repo and
  scope `rg` to a directory *inside* each — 112 repos scanned, 84 control hits.

TELL: any zero or empty you are about to reason from.
CHECK: a positive control **in the same invocation** — search for something you
know is there. Never suppress stderr on a probe whose result you will use.

Naming the enumeration is not sufficient: it can be a different program than the
one named, scoped by a file nobody mentioned (`.gitignore`), or read from the
wrong side of a mount.

## 2. Causal claims, which-knob → vary exactly one variable

*Claim: "X is what causes Y."*

Instance: a probe varied a flag *and* a pattern, attributed the difference to
the flag, and sent a peer a false confirmation of their root cause. It was the
pattern — an anchored regex against an indented line.

A two-variable probe cannot license a one-variable conclusion, and sending one
to a peer corrupts their conclusion too (§6).

## 3. Causal claims at all → hunt the counter-example

*Claim: "the mechanism is Z."*

Instance: a "deterministic 10/10" that was true of ten runs sharing one pattern
and one ordering, and false the moment either varied.

"I did not see one" is not "I looked for one."

**Advocacy is the tell.** Three over-claims in one session, all while arguing a
case: "fleet-wide" from one instance; "fd is unreliable" from an untested
example; "-h is the root cause" from an under-varied sweep. Conceding
triggers scrutiny; advocating does not. When you notice you are advocating,
re-measure the number you are leaning on.

## 4. Content claims → second independent reader

*Claim: "the file says / the output shows …"*

Instance: a search tool silently replaced everything before the first colon of
a matched line with `0`. `MARK AAA:BBB:CCC` → `1:0:BBB:CCC`.

**A positive control proves the search RAN, not that its output is INTACT.**
The control string is still found while the surrounding content is destroyed.
Rules 1–3 protect against false *absence*; this failure returns non-zero.

For anything you will quote or act on, use a second reader of a different kind:
a count claim was re-run through `git grep` — git's own matcher, not GNU grep —
and agreed. One engine's count never addressed it.

Related tell: nonsense output gets normalised — `1 matches in 0 files:` is
internally contradictory and was read as clean anyway.

## 5. Artifact claims → verify the artifact in use

*Claim: "the config/binary/tree says …"*

Ask the tool which artifact it resolves (`--show-config`,
`python -c "import X; print(X.__file__)"`) first. The tell is identical every
time: *you reach for the artifact by absolute path, because that is how you
inspect a file you believe in.*

- A config compared byte-for-byte between two agents that **neither agent's
  tool reads**; the real configuration was compiled-in defaults.
- A fix whose content was verified but whose binary never ran.
- A `--version` that lied while an editable install served an abandoned tree;
  a `.venv/bin/python` whose symlink chain read intact under `ls -la` and
  failed only at exec, its target `/usr/bin/python3.11` absent.
- **A release is not done at the tag.** PS-220's `W` default had to be read out
  of the downloaded wheel — the tag is what setuptools-scm reads; consumers
  install from PyPI.

## 6. Peer claims → corroboration must be independent in kind

Instance: scitex-dev quoted sac's own error string back to sac; sac raised its
confidence *because it came from a peer*. Two agents appearing to agree was one
source quoted twice. Ask where a peer got it before counting it as a second
source.
