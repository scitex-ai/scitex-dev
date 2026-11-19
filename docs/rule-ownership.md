# Rule ownership

**Principle.** A lint or audit rule belongs to the package whose API or
concept it enforces ([`08_linter-plugins.md`](../src/scitex_dev/_skills/general/01_ecosystem/08_linter-plugins.md)).
scitex-dev holds the engine (dispatcher, pragmas, scopes, severity machinery)
and the rules that are **cross-cutting**: rules that no single leaf package
owns. Where a rule is not clearly scoped to one leaf, we accept that it stays
in scitex-dev. Two rules may also overlap on purpose when they work at
different granularities.

Audited 2026-11-19 against `develop` of scitex-dev (f77a4952), scitex-io,
figrecipe, scitex-stats, scitex-session, scitex-clew, scitex-logging and
scitex-sdk, plus the scitex-db and scitex-agent-container plugins. To list the
live rule set, run `scitex-dev linter fingerprint <paths>`. The `rules` key
holds every effective rule and `owners` names the provider of each.

## Verdicts

| Verdict | Meaning |
|---|---|
| **a**: correct home | Already lives with its owner: a leaf rule in its leaf plugin, or an engine-mechanism rule in the engine |
| **b**: move | Clearly about one leaf's API. Moved through the handover shim (below) |
| **c**: cross-cutting | Not scoped to one leaf. Keep it in scitex-dev |
| **?**: ambiguous | More than one plausible owner, or a move blocked by work in flight. Not moved; see [Open questions](#open-questions) |

### Counts

| Surface | a | b (moved) | c | ? | total |
|---|---:|---:|---:|---:|---:|
| Linter, engine-declared `STX-*` | 1 | 6 | 18 | 10 | 35 |
| Linter, leaf-declared | 77 | 0 | 0 | 1 | 78 |
| Audit (`PS/RP/PA/SK/DJ/SR/SP/SI/REL/FM-n`) | 6 | 0 | 230 | 8 | 244 |
| **All** | **84** | **6** | **248** | **19** | **357** |

## Linter: engine-declared rules (`scitex_dev.linter._rules`)

| Rule | Checks | Concept / package | Verdict |
|---|---|---|---|
| STX-S001 | script `main()` lacks `@stx.session`/`@stx.module` | `@stx.session`: **scitex-session** | **b** → scitex-session |
| STX-S003 | `argparse` in a script (the session generates the CLI) | `@stx.session` CLI: **scitex-session** | **b** → scitex-session |
| STX-S004 | session function returns no int exit code | `@stx.session`: **scitex-session** | **b** → scitex-session |
| STX-S006 | session function does not declare every INJECTED parameter | `stx.session.INJECTED`: **scitex-session** | **b** → scitex-session |
| STX-I002 | `from scipy import stats` / `from scipy.stats import …` | `stx.stats`: **scitex-stats** | **b** → scitex-stats |
| STX-I003 | `import pickle` | `stx.io`: **scitex-io** | **b** → scitex-io |
| STX-EX001 | malformed file-level `stx-allow-file` pragma | engine pragma | a |
| STX-S002 | missing `if __name__ == "__main__"` guard | generic script structure | c |
| STX-S009 | research script sits flat under `scripts/` | research layout (project type) | c |
| STX-S010 | research script name does not start with a verb | research layout (project type) | c |
| STX-I008 | import of another package's private submodule | ecosystem boundary | c |
| STX-EH001 | narrow `except ImportError` around an optional dependency | generic Python | c |
| STX-NET001 | outbound HTTP call without `timeout` | generic Python | c |
| STX-NL001 | integer literal of 4+ digits without `_` separators | generic style | c |
| STX-HPC001 | SSH multiplexing disabled on the HPC path | ecosystem SSH hygiene (any package that shells to ssh) | c |
| STX-NM001–NM003 | mock imports, `mocker`/`monkeypatch` fixtures, mock symbols | ecosystem test doctrine | c (3) |
| STX-TQ001–TQ007 | test-quality rules (assertions, AAA markers, names, fixtures) | ecosystem test doctrine | c (7) |
| STX-I001 | `import matplotlib.pyplot` | `stx.plt`: figrecipe or scitex-plt | ? (Q1) |
| STX-I009 | `import seaborn` | `stx.plt`: figrecipe or scitex-plt | ? (Q1) |
| STX-I004 | pandas I/O instead of `stx.io` | scitex-io. **Declared but never emitted** | ? (Q2) |
| STX-I005 | numpy save/load instead of `stx.io` | scitex-io. **Declared but never emitted** | ? (Q2) |
| STX-I006 | `import random` (use the injected `rngg`) | scitex-session (injection) or scitex-repro (RNG) | ? (Q3) |
| STX-I007 | `import logging` (use the injected `logger`) | scitex-session or scitex-logging | ? (Q4) |
| STX-P010 | top-level `figrecipe` inside an `@stx.session` module | scitex-session (injection) or figrecipe (`P` namespace) | ? (Q5) |
| STX-S005 | missing `import scitex as stx` | umbrella `scitex` | ? (Q7) |
| STX-S007 | `load_configs()` result not UPPER_CASE | scitex-io (`load_configs`) or scitex-session (`CONFIG`) | ? (Q8) |
| STX-S008 | hard-coded analysis parameter (should come from `CONFIG`) | scitex-session (`config/*.yaml` → `CONFIG`) | ? (Q9) |

## Linter: leaf-declared rules

| Rules | Checks | Owner | Verdict |
|---|---|---|---|
| STX-IO001–IO019 (19) | raw numpy/pandas/pickle/json/yaml/torch/joblib/h5py/image/sqlite/pathlib/shutil I/O; extensions with no handler | scitex-io | a |
| STX-PA001–PA005 (5) | absolute or unprefixed paths in `stx.io` calls; bare `open()`; `makedirs`; `chdir` | scitex-io | a |
| STX-ST001–ST006 (6) | raw `scipy.stats` tests that have a `stx.stats` equivalent | scitex-stats | a |
| STX-P001–P004, P006–P009 (8) | plotting calls and style-override kwargs | figrecipe | a |
| STX-FM001–FM013, FM016–FM019 (17) | figure/mm layout and figure doctrine | figrecipe | a (see note) |
| STX-FIG001 (1) | subplots that disagree on axis ranges | figrecipe | a |
| STX-UI101–UI116 (16) | shared UI shell, theme and CSS contracts | scitex-sdk (successor of scitex-ui) | a |
| PS-220 (1) | output under `src/` must go through scitex-logging | scitex-logging (mandatory provider) | a |
| STX-DB001 (1) | `SQLite3(...)` file is outside `stx.io` provenance | scitex-db | a |
| STX-SAC001, SAC002, SAC004 (3) | A2A v0 AgentCard fields and method names | scitex-agent-container | a |
| STX-P005 (1) | `print()` inside `@stx.session`. figrecipe declares it, but the **engine emits it** | figrecipe declares; output routing is a logging/session concern | ? (Q6) |

scitex-clew registers a plugin with no rules yet (placeholder).

**Residual (FM).** figrecipe owns FM001–FM009, but the checker that emits
them (`scitex_dev.linter._fm_checker.FMChecker`) is still in scitex-dev and
is passed through figrecipe's payload. That checker belongs in figrecipe and
is the next candidate move (no ownership question, only the code location).

**Overlap kept on purpose** (the two rules work at different granularities):
- I003 (import) and IO005 (calls)
- I002 (import) and ST001–ST006 (calls)
- I001 (import) and FM016 / the raw-matplotlib checker (figure creation)
- P005 (print in a session) and PS-220 (print in `src/`)

## Audit rules (`scitex-dev audit-*`, skills install)

These enforce **ecosystem conventions on every package**: layout, README,
CI, docs, skills, Django layout and release metadata. That makes them
cross-cutting by construction (c). The audit-project plugin group also needs
the providing package installed in every audited environment. A rule that
moves to a leaf therefore has to become a *mandatory* provider, as PS-220 is,
or its coverage silently disappears where that leaf isn't installed. That is
the bar any audit-rule move has to clear.

| Family | Ids | Command | Verdict |
|---|---|---|---|
| PS §1 layout/README/docs/community | 85 ids: PS-101–119 (+108b, 110b), 121–139 (+138b), 141–147, 150–164, 166–169, 173, 180–183, 218, 219, 224–229, 231, 232, HOOK-001, PATH-001/002 | audit-project | c, except PS-182, PATH-001, PATH-002 (?) |
| PS §2 src/tests | 16 ids: PS-140, 165, 201–207 (+206b), 210–212, 220, 223, 230 | audit-project | c, except PS-220 (a, scitex-logging) |
| PS §3 deps/tests/examples/workflows | 17 ids: PS-148, 149, 213 (+213i), 214–217, 221, 233, 235, 236, 301–303, CLEW-001, AGENT-001 | audit-project | c, except CLEW-001, AGENT-001 (?) |
| PS §4/§5/§13 | 15 ids: PS-401, 402, 222, 234, 501–508, HOOK-010–012 | audit-project | c, except PS-234 (a, scitex-dev's own plugin), PS-501, PS-503 (?) |
| PS-SDK-HEADER/FILTER/SHELL/WEB | 4 | audit-project (scitex-sdk plugin) | a |
| RP-201, 202, 204, 205 | 4 | audit-project (research projects) | c |
| PA-101–104, 201–203, 301, 304–307, 501 | 13 | audit-api | c, except PA-305 (?) |
| SK-101–111, 201–203, 210, 211, 301, 302, 401, 601, 701–711 | 31 | audit-skills | c (scitex-dev owns the skills convention) |
| DJ-101–110, 201–204, 301, 302, 401, 402, 501–503 | 21 | audit-django | c (Django layout for any app; scitex-hub is the reference, not the owner) |
| SR-101–105, SP-101–102/201–202/301–302/401–404, SI-100–103/200–203 | 23 | skills install / projection | c |
| REL-5, 9, 10, 11, 12, 21, 31, 41 | 8 | ecosystem audit-summary | c |
| FM-0 … FM-6 (frontmatter; not the figure `STX-FM*`) | 7 | quality | c |

## Moved in this change: the handover shim

Six engine rules moved to their owners. Ids, severities, categories,
messages, suggestions, `requires` gates and scopes are all unchanged:

| Rule(s) | Now emitted by |
|---|---|
| STX-S001, S003, S004, S006 | `scitex_session._linter_plugin` (new `session` entry point) |
| STX-I002 | `scitex_stats._linter_plugin` |
| STX-I003 | `scitex_io._linter.import_checker` |

How it works ([`_rules/_handover.py`](../src/scitex_dev/linter/_rules/_handover.py)):

1. `HANDOVER` maps each moved id to the **one** distribution allowed to take
   it over. The loader accepts that provider's declaration instead of raising
   it as an engine collision. `SciTeXChecker` then stops emitting the id, and
   the leaf's checker emits it. Any other provider that declares the id still
   fails as a collision.
2. Both sides emit through the same gate, `spi.add_issue`: `requires`,
   `disable`, `# stx-allow`, the per-rule severity pin, and the category
   floor (research projects). Severities per project type are therefore
   identical by construction.
3. **Compatibility shim.** When the owner is not installed, or is an older
   release without the plugin, the engine copy keeps emitting the rule
   exactly as before.
4. **Removal (follow-up).** Once the leaf releases are on PyPI and pinned
   where these rules must fire, delete the engine definitions, their emission
   sites and the `HANDOVER` rows. The leaf tests that assert "metadata ==
   engine copy" go with them.

**Equivalence evidence** (`scitex-dev linter fingerprint`). The fingerprint
covers every effective rule's metadata, every finding as `[file, line, col,
id, severity, category, message]`, and the corpus file hashes. It was taken
on a fixed corpus before the move (all `develop`) and after it (the three
leaf branches installed and `handed_over` active for all six ids).

| Corpus | Files | Rules | Findings | Diff |
|---|---:|---:|---:|---|
| `examples/` of scitex (umbrella), scitex-session, scitex-io, scitex-stats, figrecipe, scitex-clew, scitex-writer, and `scripts/` of paper-scitex-clew | 1172 | 109 | 5375 | identical |
| Targeted corpus: plain and `project-type: research` trees with per-rule pins, `disable`, `# stx-allow`, async and kw-only signatures | 3 | 109 | 18 | identical |

The moved rules account for these findings in the first corpus:
S001 = 88, S003 = 10, S004 = 21, S006 = 112, I002 = 16. I003 has no hits
there, so the targeted corpus covers it (6 findings).

One known non-difference: issues on the **same line with the same severity**
can be listed in a different order, because plugin findings are appended
after engine findings. The fingerprint compares the sorted set, and the set
is identical.

## Open questions

Ambiguous rules were **not** moved. Each question has options and a
recommendation.

- **Q1, STX-I001 / I009** (`matplotlib.pyplot` / `seaborn` imports → `stx.plt`).
  Candidate owners are (A) figrecipe, which already owns P*/FM*/FIG001 and
  the raw-matplotlib checker, or (B) scitex-plt, the `stx.plt` wrapper.
  **Recommend A**, through the same handover. The research `error` pins for
  I001/I009 survive because `add_issue` applies them.
- **Q2, STX-I004 / I005.** These are declared but no code emits them. They
  were superseded by scitex-io IO003/IO004 and IO001/IO002. Options:
  (A) retire them (delete, with a CHANGELOG note) or (B) move the dead
  metadata into scitex-io. **Recommend A.** They currently show up in
  `list-rules` as if they were active.
- **Q3, STX-I006** (`import random` → injected `rngg`). Candidates are
  (A) scitex-session, which injects `rngg`, or (B) scitex-repro, which
  implements it. **Recommend A**, because the rule's message is about the
  injection.
- **Q4, STX-I007** (`import logging` → injected `logger`). It fires in every
  file, not only in sessions. Candidates are (A) scitex-logging, alongside
  PS-220, or (B) scitex-session. **Recommend A**, so that one package owns
  "use scitex-logging".
- **Q5, STX-P010** (top-level `figrecipe` inside a session → injected
  `plt`). Candidates are (A) scitex-session, which owns the injection
  contract (the engine's own docstring says so), or (B) figrecipe, which owns
  the `P` id namespace. **Recommend A**, keeping the id.
- **Q6, STX-P005** (`print()` in a session). figrecipe declares it, but the
  engine emits it. Options: (A) move the emission into figrecipe (a code
  move only); (B) re-home the rule to scitex-session, since it fires only
  inside `@stx.session`; (C) re-home it to scitex-logging and fold it into
  PS-220. **Recommend B.** It is about the injected logger, not plotting.
- **Q7, STX-S005** (`import scitex as stx`). The concept is the umbrella
  import. That conflicts with SK-601, PA-304 and PS-139, which discourage
  the umbrella in leaves and skills. **Recommend** keeping it in scitex-dev
  (c) until the umbrella-vs-leaf import doctrine is settled. The rules
  currently give opposite advice.
- **Q8, STX-S007** (`CONFIG = load_configs()` naming). Candidates are
  (A) scitex-io, which defines `load_configs`, or (B) scitex-session, which
  injects `CONFIG`. **Recommend A**, because the rule matches calls to
  scitex-io's function.
- **Q9, STX-S008** (magic numbers → `config/*.yaml` → `CONFIG`). By "where
  `CONFIG` lives", the owner is scitex-session: its `_lifecycle` loads
  `config/*.yaml` into the injected `CONFIG`. There is no scitex-config
  `CONFIG` API. But the rule is under active change: 0.64.x, plus open
  branches `fix/s008-fewer-false-positives-1119` and
  `feat/s008-analysis-params-1119`. It also fires on non-session scripts and
  carries a ~780-line heuristics module. **Recommend** deferring, then moving
  it to scitex-session through the handover once the S008 branches land.
- **Q10, PS-501 / PS-503** (examples use `@stx.session` and have committed
  `FINISHED_SUCCESS`). The concept is scitex-session, but these enforce the
  ecosystem's examples convention on every package, and scitex-session is
  not installed everywhere audits run. **Recommend** keeping them (c).
- **Q11, PS-PATH-001 / 002** (`config/PATH.yaml` shape for `CONFIG.PATH`).
  The concept is scitex-session. **Recommend** moving them only together
  with making scitex-session a *mandatory* audit-project provider for
  research projects (as PS-220 is for logging). Otherwise keep them.
- **Q12, PS-CLEW-001 / PS-AGENT-001** (`add_claim` without verification or a
  `claims.json` write). The concept is scitex-clew. **Recommend** moving
  them to a scitex-clew audit plugin after the in-flight claim-metadata and
  F15 work lands, with the same mandatory-provider caveat as Q11.
- **Q13, PS-182** (hand-rolled local-state resolver → `scitex_config`).
  **Recommend** keeping it (c). It polices every package, and the remedy only
  happens to live in scitex-config.
- **Q14, PA-305** (playwright module lacks `capture_debug_artifacts_async`
  from scitex-browser). **Recommend** moving it to a scitex-browser audit
  plugin, or retiring it if the requirement is obsolete.

## How to move a rule

1. Add `"<id>": "<owner-distribution>"` to `HANDOVER`.
2. In the owner, declare the rule with identical metadata and a checker that
   emits it through `spi.add_issue`, then register the plugin entry point.
   Pin `scitex-dev>=` the release that has `HANDOVER` and `spi.add_issue`.
3. Run `scitex-dev linter fingerprint <corpus> --out before.json` on
   `develop`. Install the owner branch and run
   `scitex-dev linter fingerprint <corpus> --against before.json`. It must
   print `identical`.
4. After the owner release is on PyPI and pinned, remove the engine copy.
