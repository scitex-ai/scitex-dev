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
| **r**: retired | Never fired; id kept reserved (`_rules/_retired.py`) |
| **?**: on hold / pending | A doctrine question, or a move waiting for in-flight work. See [Open questions](#open-questions) |

The first audit listed 19 ambiguous rules. The decisions taken on 2026-11-19
are recorded in [Decisions](#decisions-2026-11-19); the tables below show
the result.

### Counts

| Surface | a | b (moved) | c | r | ? | total |
|---|---:|---:|---:|---:|---:|---:|
| Linter, engine-emitted `STX-*` (incl. P005) | 1 | 14 | 18 | 2 | 1 (S005, held) | 36 |
| Linter, leaf-declared (excl. P005) | 77 | 0 | 0 | 0 | 0 | 77 |
| Audit (`PS/RP/PA/SK/DJ/SR/SP/SI/REL/FM-n`) | 6 | 0 | 236 | 0 | 2 (PS-CLEW/AGENT, pending) | 244 |
| **All** | **84** | **14** | **254** | **2** | **3** | **357** |

STX-P005 is counted with the engine rules. figrecipe declared it, but the
engine emitted it, and it now moves to scitex-session.

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
| STX-I001 | `import matplotlib.pyplot` | `stx.plt`: **figrecipe** | **b** → figrecipe |
| STX-I009 | `import seaborn` | `stx.plt`: **figrecipe** | **b** → figrecipe |
| STX-I004 | pandas I/O instead of `stx.io` | covered by scitex-io IO003/IO004 | **r** (never fired) |
| STX-I005 | numpy save/load instead of `stx.io` | covered by scitex-io IO001/IO002 | **r** (never fired) |
| STX-I006 | `import random` (use the injected `rngg`) | session injection: **scitex-session** | **b** → scitex-session |
| STX-I007 | `import logging` (use the injected `logger`) | **scitex-logging** (with PS-220) | **b** → scitex-logging |
| STX-P010 | top-level `figrecipe` inside an `@stx.session` module | session injection: **scitex-session** | **b** → scitex-session |
| STX-P005 | `print()` once a session is seen (figrecipe declared it; the engine emitted it) | session injection: **scitex-session** | **b** → scitex-session |
| STX-S005 | missing `import scitex as stx` | umbrella `scitex` | **?** held: doctrine question (Q7) |
| STX-S007 | `load_configs()` result not UPPER_CASE | `load_configs`: **scitex-io** | **b** → scitex-io |
| STX-S008 | hard-coded analysis parameter (should come from `CONFIG`) | `config/*.yaml` → `CONFIG`: **scitex-session** | **b** → scitex-session (detector ported verbatim) |

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

scitex-clew registers a plugin with no rules yet (placeholder).

**FM checker.** figrecipe owns FM001–FM009. The checker that emits them,
formerly `scitex_dev.linter._fm_checker.FMChecker`, now ships in figrecipe
(`figrecipe._quality._fm_checker`) as a verbatim port. figrecipe declares the
`fm-checker` capability, and when it does, the engine skips its own copy.
That copy stays as the compatibility shim for an older figrecipe.

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
| PS §1 layout/README/docs/community | 85 ids: PS-101–119 (+108b, 110b), 121–139 (+138b), 141–147, 150–164, 166–169, 173, 180–183, 218, 219, 224–229, 231, 232, HOOK-001, PATH-001/002 | audit-project | c (PS-182 and PATH-001/002 included, by decision) |
| PS §2 src/tests | 16 ids: PS-140, 165, 201–207 (+206b), 210–212, 220, 223, 230 | audit-project | c, except PS-220 (a, scitex-logging) |
| PS §3 deps/tests/examples/workflows | 17 ids: PS-148, 149, 213 (+213i), 214–217, 221, 233, 235, 236, 301–303, CLEW-001, AGENT-001 | audit-project | c, except CLEW-001, AGENT-001 (?, move pending) |
| PS §4/§5/§13 | 15 ids: PS-401, 402, 222, 234, 501–508, HOOK-010–012 | audit-project | c, except PS-234 (a, scitex-dev's own plugin). PS-501/503 are c by decision |
| PS-SDK-HEADER/FILTER/SHELL/WEB | 4 | audit-project (scitex-sdk plugin) | a |
| RP-201, 202, 204, 205 | 4 | audit-project (research projects) | c |
| PA-101–104, 201–203, 301, 304–307, 501 | 13 | audit-api | c (PA-305 included, see Decisions) |
| SK-101–111, 201–203, 210, 211, 301, 302, 401, 601, 701–711 | 31 | audit-skills | c (scitex-dev owns the skills convention) |
| DJ-101–110, 201–204, 301, 302, 401, 402, 501–503 | 21 | audit-django | c (Django layout for any app; scitex-hub is the reference, not the owner) |
| SR-101–105, SP-101–102/201–202/301–302/401–404, SI-100–103/200–203 | 23 | skills install / projection | c |
| REL-5, 9, 10, 11, 12, 21, 31, 41 | 8 | ecosystem audit-summary | c |
| FM-0 … FM-6 (frontmatter; not the figure `STX-FM*`) | 7 | quality | c |

## Moved in this change: the handover shim

Fourteen rules moved to their owners. Ids, severities, categories, messages,
suggestions, `requires` gates and scopes are all unchanged:

| Rule(s) | Now emitted by |
|---|---|
| STX-S001, S003, S004, S006, S008 | `scitex_session._linter_plugin` (new `session` entry point; the S008 detector is ported verbatim into `_linter_s008/`) |
| STX-I006, P010, P005 | `scitex_session._linter_injection` |
| STX-I001, I009 | `figrecipe._quality._import_checker` |
| STX-I002 | `scitex_stats._linter_plugin` |
| STX-I003, S007 | `scitex_io._linter.import_checker`, `scitex_io._linter.config_naming` |
| STX-I007 | `scitex_logging._linter_plugin` |
| FM001–FM009 (checker code only) | `figrecipe._quality._fm_checker` (`fm-checker` capability) |

Retired: **STX-I004 / STX-I005**. Neither has had an emitter since the
per-package migration, and scitex-io's IO001–IO004 cover what they
described. Both ids stay **reserved** (`_rules/_retired.py`):
- a plugin that declares either id fails to load;
- `from scitex_dev.linter.rules import I004` still works;
- a config that still names either id gets a `DeprecationWarning` naming the
  successor rules.

How the handover works ([`_rules/_handover.py`](../src/scitex_dev/linter/_rules/_handover.py)):

1. **One named owner.** `HANDOVER` maps each moved id to the **one**
   distribution allowed to take it over. The loader accepts that provider's
   declaration instead of raising an engine collision. `SciTeXChecker` then
   stops emitting the id, and the leaf's checker emits it. Any other provider
   that declares the id still fails as a collision.
2. **Plugin-to-plugin moves (STX-P005).** When the predecessor plugin
   (figrecipe) and the owner (scitex-session) both declare the id, the
   owner's declaration wins whichever loads first, and the predecessor's is
   recorded under `superseded`. The predecessor therefore keeps declaring the
   id until the owner's release is pinned, and no mixed-version install loses
   the rule.
3. **Same emission gate.** Both sides emit through `spi.add_issue`, which
   applies `requires`, `disable`, `# stx-allow`, the per-rule severity pin
   and the category floor. Severities per project type are identical by
   construction. The research `error` pins for I001/I002/I009 and the
   `warning` pin for S008 still apply.
4. **Feature detection where there is no pin.** scitex-logging does not
   depend on scitex-dev, and figrecipe pins an older one. Both declare their
   new ids only when the installed scitex-dev's `HANDOVER` names them as the
   owner. On an older engine they declare nothing new, and the engine keeps
   emitting its own copy.
5. **Compatibility shim.** When the owner is not installed, or is an older
   release, the engine copy keeps emitting the rule exactly as before.
6. **Removal (follow-up).** Once the leaf releases are on PyPI and pinned
   where these rules must fire, delete the engine definitions, their emission
   sites, `_fm_checker.py`, `_magic_numbers*.py` and the `HANDOVER` rows. At
   the same time:
   - figrecipe drops its P005 declaration;
   - the leaf tests that assert "metadata == engine copy" go too.

Caveat for STX-P005. Before, the rule needed figrecipe installed, because
figrecipe declared it. Now it needs scitex-session, which declares it. In
practice the two are installed together (scitex-session pulls in scitex-plt,
which pulls in figrecipe), so no corpus here shows a difference.

**Equivalence evidence** (`scitex-dev linter fingerprint`). The fingerprint
covers every effective rule's metadata, every finding as `[file, line, col,
id, severity, category, message]`, and the corpus file hashes.
- **Before:** all `develop` on 2026-11-19 (scitex-dev 3cce4fd2, which
  includes both merged S008 PRs).
- **After:** the five leaf branches installed and `handed_over` active for
  all 14 ids, with P005 superseded and `fm-checker` declared.

| Corpus | Files | Findings | Diff |
|---|---:|---:|---|
| `examples/` of scitex (umbrella), scitex-session, scitex-io, scitex-stats, figrecipe, scitex-clew and scitex-writer, plus `scripts/` of paper-scitex-clew | 1172 | 5375 | identical findings |
| Targeted corpus 1: plain/research trees, per-rule pins, `disable`, `# stx-allow`, async and kw-only signatures | 3 | 18 | identical findings |
| Targeted corpus 2: I001/I009/I006/I007/P010/P005/S007/FM001–FM009 shapes, P005 order-dependence, `src/` exemption, research promotions | 3 | 41 | identical findings |

The rule set differs in exactly one way: STX-I004 and STX-I005 are absent,
which is the intended retirement (109 → 107 rules). Hits for the moved rules
in the first corpus:

| Rule | Hits | Rule | Hits |
|---|---:|---|---:|
| S001 | 88 | I006 | 17 |
| S003 | 10 | I007 | 5 |
| S004 | 21 | I009 | 3 |
| S006 | 112 | P010 | 139 |
| S008 | 666 | P005 | 262 |
| I001 | 81 | S007 | 1 |
| I002 | 16 | FM001 / FM002 / FM006 | 112 / 97 / 92 |

The shim path also gives identical findings: the new engine with every leaf
on develop, so nothing is handed over. So does the reverse mix: the
**develop** engine with the new figrecipe and scitex-logging. The fingerprint
is fully identical there, including the rule set, because both leaves'
feature detection leaves the rules to the old engine.

One known non-difference: issues on the **same line with the same severity**
can be listed in a different order, because plugin findings are appended
after engine findings. The fingerprint compares the sorted set, and the set
is identical.

## Decisions (2026-11-19)

| Rule(s) | Decision |
|---|---|
| I001, I009 | → figrecipe |
| I004, I005 | retired, ids reserved |
| I006, P010, P005 | → scitex-session |
| I007 | → scitex-logging |
| S007 | → scitex-io |
| S008 | → scitex-session; both open S008 PRs (#1065, #1072) had landed |
| FM001–FM009 checker | → figrecipe |
| PS-501/503, PS-182, PS-PATH-001/002 | stay in scitex-dev (cross-cutting conventions) |
| PS-CLEW-001, PS-AGENT-001 | → scitex-clew audit plugin **after** the in-flight clew work (#227, #228) lands; not moved yet |
| PA-305 | **kept in scitex-dev** (see below) |
| S005 | **on hold**: doctrine question taken to the user |

Why PA-305 stays. Its natural concept owner is scitex-browser, since it
checks for `capture_debug_artifacts_async`. Moving it is not possible yet,
and retiring it is not justified:
- **No home for the rule.** PA-305 runs in `audit-api`, which has no plugin
  group, so scitex-browser has nowhere to put it. A move would mean building
  that plugin group and making scitex-browser a mandatory provider wherever
  audits run.
- **The rule is live.** It is enforced on every package that drives
  Playwright. Its doctrine lives in scitex-dev's own skill
  `02_package/09_browser-automation-debugging.md`, so retiring it would drop
  live coverage.

So it stays as a cross-cutting dev convention (c). If `audit-api` grows a
plugin group, revisit.

## Open questions

- **Q7, STX-S005** (`import scitex as stx`): on hold. The rule conflicts with
  SK-601, PA-304 and PS-139, which discourage the umbrella import in leaves
  and skills. The user decides the doctrine first.
- **Q12, PS-CLEW-001 / PS-AGENT-001:** move to a scitex-clew audit plugin
  (`scitex_dev.audit.project` group) once scitex-clew #227 and #228 land.
  Same zero-change method, with the provider made mandatory for research
  projects so coverage cannot silently drop.

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
