---
description: |
  [TOPIC] Packaging and release failures — the repo is right, the published artifact is wrong
  [DETAILS] Recipes §3, §4, §6, §7, §8, §10 and §11 of the failure playbook: PyPI trusted-publisher setup and its silent-save gotcha, wheel-content drift (git has the module, PyPI doesn't), extras-completeness for umbrella bridges, Doc-Drift CI installing from PyPI instead of the checkout, the implicit-transitive-dep class-action that only a fresh-venv install catches, the PostToolUse CI watcher that closes the loop, and the orphan License classifier that blocks setuptools 80+ builds. Triage table in the sibling `01_failure-playbook.md`; the in-tree counterpart is `06_compat-and-refactor-drift.md`. Use when a consumer install fails but the checkout looks fine.
tags: [scitex-general-quality-packaging-failures]
---

# Packaging and Release Failures

Recipes reached from the triage table in
[01_failure-playbook.md](01_failure-playbook.md). Section numbers are the
playbook's originals, so a cross-reference elsewhere in the tree still resolves.

Every failure here is one shape:

> **The repo is right and the artifact consumers get is wrong.**

An editable dev install, a green *Test* job, and a pushed tag can all agree
while the published package is broken — the dev environment already has every
dependency, so nothing declares itself missing. Detection therefore always
means stepping *outside* the checkout: a fresh venv, a downloaded wheel, the
PyPI index. The in-tree counterpart — where nothing was published wrong but
something the code references moved — is
[06_compat-and-refactor-drift.md](06_compat-and-refactor-drift.md).

## 3. PyPI trusted-publisher setup (silent-save gotcha)

The **first** release of any new PyPI project must be `twine upload` from a local build — trusted publishing cannot create a new project. Afterwards, configure the trusted publisher at:

```
https://pypi.org/manage/project/<pkg>/settings/publishing/
```

Fields: owner `ywatanabe1989`, repo `<pkg>`, workflow `publish-pypi.yml`, environment `pypi`.

**Silent-save gotcha** — after submit, the "Manage current publishers" list must actually show the new entry. If it still says *"No publishers are currently configured"*, the form didn't persist. Re-enter it. This is the single most common cause of `invalid-publisher` errors on a tag-triggered publish when the package already exists on PyPI. Once configured, `gh run rerun <id>` — no retag needed.

**Probe** (tag ↔ PyPI alignment):

```bash
for r in ~/proj/scitex-*; do
  [ -f "$r/pyproject.toml" ] || continue
  pkg=$(basename $r)
  tag=$(git -C $r tag --sort=-v:refname | head -1)
  pypi=$(curl -s https://pypi.org/pypi/$pkg/json \
         | python3 -c "import sys,json;d=json.load(sys.stdin);print('v'+d['info']['version'])" 2>/dev/null)
  [ -n "$tag" ] && [ -n "$pypi" ] && [ "$tag" != "$pypi" ] && echo "$pkg: tag=$tag pypi=$pypi"
done
```

## 4. Wheel-content drift (git has it, PyPI doesn't)

When downstream tests `ModuleNotFoundError` a submodule that clearly exists in `src/` on develop, the PyPI wheel was cut before that module landed. Verify:

```bash
pip download <pkg>==<pypi-version> --no-deps -d /tmp/check
python3 -c "import zipfile,os;p='/tmp/check';w=[f for f in os.listdir(p) if f.endswith('.whl')][0];z=zipfile.ZipFile(os.path.join(p,w));print([n for n in z.namelist() if 'submodule_name' in n])"
```

**Fix:** bump the package version, tag, push — publishes the current state. Never "fix" downstream by pinning to an older version; fix the upstream release.

Session hit: `scitex-dev 0.6.1` on PyPI lacked `_skills_quality_pytest.py`; released 0.7.0 to unblock 10 downstream CIs.

## 6. Extras-completeness (empty `[foo]` breaks umbrella bridges)

Every bridge directory under `src/scitex/<name>/` that re-exports a standalone package must have its extra populated. Empty `[container] = []` leaves `stx.container.apptainer` unreachable from `pip install scitex[all]`; Doc-Drift flags every chain.

**Probe (inside scitex-python):**

```bash
python3 -c "
import tomllib, pathlib
d = tomllib.loads(open('pyproject.toml','rb').read())
extras = d['project']['optional-dependencies']
bridges = [p.name for p in pathlib.Path('src/scitex').iterdir()
           if p.is_dir() and not p.name.startswith('_')]
for b in bridges:
    if b in extras and extras[b] == []:
        print(f'EMPTY: scitex[{b}] but src/scitex/{b}/ exists')
"
```

**Fix:** `container = ["scitex-container"]`, `dataset = ["scitex-dataset"]`, etc.

A stricter form of this check — *every canonical ecosystem package must appear
in some named extra AND in `[all]`* — is §14 of
[07_release-gate-probes.md](07_release-gate-probes.md).

## 7. Doc-Drift CI install source

`doc-drift-nightly.yml` must install scitex from **the current checkout** (`pip install ".[all]"`) rather than from PyPI (`pip install "scitex[all]"`). Otherwise a pyproject.toml fix in the same push won't take effect until a PyPI release catches up.

The workflow's `on: push: paths:` filter also excludes `pyproject.toml` — force a run with `gh workflow run "Doc-Drift Nightly" --ref develop` after the push.

## 8. Implicit transitive dep after a refactor (the 2026-04-28 class-action)

**Symptom.** `pip install <pkg>==<latest>` in a fresh venv fails with
`ModuleNotFoundError: No module named 'scitex_config'` (or any other
ecosystem package). CI's *Test* job is green because the dev environment
has the dep installed editable; only the *Install Test (fresh venv)* job
catches it.

**Root cause.** A migration sweep edits `src/<pkg>/...` to `from
scitex_config._ecosystem import local_state` but doesn't audit
`pyproject.toml` for the new transitive dep. The package now imports
something it doesn't declare, so PyPI consumers hit ModuleNotFoundError.

**Detection** is automated in
`scitex-dev/scripts/quality/audit_ecosystem.py` (`§C5 src imports
scitex_config but pyproject does not declare scitex-config`). The
nightly `quality-audit.yml` workflow opens a tracking GitHub issue
tagged `quality-audit` if any CRITICAL findings appear.

**Fix recipe.**

1. Add the dep to `dependencies = [...]` (NOT `optional-dependencies`).
2. Bump the patch version (`0.1.9 → 0.1.10`).
3. `git tag v<new>` and push tags. If the publish workflow uses
   `event: release` instead of `push: tags: ['v*']`, also create a
   `gh release create v<new>` so PyPI publish actually fires.
4. Verify on PyPI with `pip index versions <pkg>` — a pushed tag without
   a corresponding release is invisible to consumers.

**Affected on 2026-04-28 (all fixed + republished):** scitex-core 0.2.5,
scitex-container 0.1.10, scitex-browser 0.1.11, scitex-dataset 0.3.5,
scitex-decorators 0.1.4, scitex-template 0.6.1.

Its silent twin — the same migration breaking *tests* rather than the
install — is §9 of
[06_compat-and-refactor-drift.md](06_compat-and-refactor-drift.md).

## 10. PostToolUse CI watcher closes the loop end-to-end

`~/.claude/hooks/post-tool-use/check_ci_status.sh` emits
`WARN  CI FAILURE  ...` to stderr + `exit 2` so Claude Code forwards the
message to the assistant on every tool call inside a git repo. Pair it
with the `speak-and-call` directive ("don't continue past a WARN").
Without the watcher, the bugs from §8 and §9 stay silent until a human
notices PyPI is broken.

The companion `audit_ecosystem.py` script runs nightly, opens a
GitHub issue tagged `quality-audit` on CRITICAL/HIGH, and uploads the
full JSON as an artifact.

## 11. Orphan License classifier blocks setuptools 80+ build (the 2026-04-28b class-action)

**Symptom.** ``pip install -e .`` fails with
``setuptools.errors.InvalidConfigError: License classifiers have been
superseded by license expressions``. CI's *Test* / *Tests* job aborts
before any test runs.

**Root cause.** PEP 639 deprecated the legacy
``"License :: OSI Approved :: ..."`` classifier in favour of the
``license = "AGPL-3.0-only"`` SPDX expression. setuptools 80+ refuses
the build when *both* are present. After our 2026-04-28a normalization
to SPDX (REL-11), 41 ecosystem packages still carried the legacy
classifier alongside the new SPDX form.

**Detection** is automated in
`scitex_dev._pyproject_lint.check_orphan_license_classifier`
(rule ``E5C13_orphan_license_classifier``, severity HIGH).

**Fix.** Remove the classifier line; SPDX is authoritative now:

```toml
[project]
license = "AGPL-3.0-only"
classifiers = [
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    # "License :: OSI Approved :: GNU Affero General Public License v3",  ← drop
]
```

**Affected on 2026-04-28 (all 31 fixed + republished):** crossref-local,
figrecipe, openalex-local, scitex-agent-container, scitex-audio,
scitex-audit, scitex-browser, scitex-clew, scitex-compat, scitex-core,
scitex-dataset, scitex-db, scitex-dict, scitex-etc, scitex-gists,
scitex-io, scitex-logging, scitex-notification, scitex-orochi,
scitex-parallel, scitex-path, scitex-plt, scitex-repro, scitex-scholar,
scitex-stats, scitex-str, scitex-template, scitex-types, scitex-writer,
socialia, scitex-python.
