---
description: |
  [TOPIC] Packaging and release failures — the repo is right, the published artifact is wrong
  [DETAILS] Recipes §3, §4, §6, §7, §8, §10 and §11: publisher identity, artifact contents, complete install profiles, source-versus-installed documentation, runtime dependencies, CI evidence and license metadata. Use owning source and actual release gates; preserve failures instead of forcing reruns or changing upload routes.
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

PyPI supports a pending Trusted Publisher that creates a project on its first
successful publication. A manual first upload is not required, and a pending
publisher does not reserve the name. See the
[official PyPI guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

For an existing project, inspect the configured publisher at:

```
https://pypi.org/manage/project/<pkg>/settings/publishing/
```

Match the repository owner/name, workflow filename and environment to the leaf's
actual workflow. Do not copy a historical account or workflow name. Dev's
current boundary is declared in
`.github/workflows/pypi-publish-and-github-release-on-tag.yml` and checked by
`.github/ci/release-identity.py`.

After authorized configuration, verify that the intended publisher is listed.
For `invalid-publisher`, compare its fields with the actual OIDC claims and
workflow; do not infer that an unsaved form is the cause. Preserve unsuccessful
qualification evidence. This recipe does not authorize forced CI reruns,
moving tags or an alternate uploader. Follow the
[current release flow](../05_development/18_end-to-end-release-flow.md).

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

**Fix:** repair the owning package's source or packaging configuration, then
qualify a new unused version through its actual release stages. A tag push
alone does not establish publication or artifact correctness. Keep consumers
on a compatible qualified release until its replacement is verified; do not
replace a failed candidate with relaxed gates or dependency overrides.

Session hit: `scitex-dev 0.6.1` on PyPI lacked `_skills_quality_pytest.py`; released 0.7.0 to unblock 10 downstream CIs.

## 6. Extras-completeness (empty `[foo]` breaks umbrella bridges)

A bridge in the checkout does not establish that the normal installed profile
supplies its provider. Inspect core dependencies, public extras and guarded
optional imports before changing them. Do not prescribe a new per-feature
extra from a directory name alone.

PS-221 checks public-extra closure in
`src/scitex_dev/_cli/audit/_project/_check_extras_all_closure.py`: public
requirements must be included in `all`, including through valid self-references.
This static check does not resolve dependency compatibility or establish that
every advertised operation works. Its original controls are in
`tests/scitex_dev/_cli/audit/_project/test__check_extras_all_closure.py`.

Repair the owning declarations and qualify the complete normal profile in a
fresh environment. Do not retry a failed `all,dev` install with a smaller extra,
bare install, `--no-deps` or overrides and report it as the same acceptance.

## 7. Doc-Drift CI install source

Distinguish checks of the changed checkout from checks of an installed or
published distribution. A source change cannot repair a stale public wheel
being imported by that check. Record the module path, source SHA and installed
version; use the workflow's complete declared profile.

Dev's actual quality workflow is
`.github/workflows/scitex-dev-quality-audit-on-ubuntu-latest.yml`. It audits the
editable checkout; its path filters include `pyproject.toml`. Inspect the leaf's
current triggers instead of assuming a historical nightly name or forcing
another run. Build success is not content acceptance; follow the
[documentation drift skill](../05_development/22_documentation-drift.md).

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

**Detection:** PS-233 checks runtime import locations against declarations;
see the final section below. Dev dispatches owning audit providers. Retain
fresh normal install and actual import/operation checks: an AST finding alone
cannot qualify the resolved installed graph.

**Fix recipe.**

1. Add an unguarded runtime dependency to `dependencies`. A genuinely optional
   guarded capability follows its owning package's declared extra instead;
   retain the location-sensitive PS-233 controls described below.
2. Select an unused version and follow the owning
   [release procedure](../05_development/18_end-to-end-release-flow.md), including
   all exact-head checks, the complete declared profile and artifact identity.
3. Inspect the leaf's actual validation and publication triggers. Push only the
   intended immutable tag. Do not create a second GitHub release or uploader
   when the workflow already owns that operation.
4. Verify wheel/sdist contents and a normal dependency-compatible installation
   from the published artifacts. Index visibility alone is not acceptance.

**Affected on 2026-04-28 (all fixed + republished):** scitex-core 0.2.5,
scitex-container 0.1.10, scitex-browser 0.1.11, scitex-dataset 0.3.5,
scitex-decorators 0.1.4, scitex-template 0.6.1.

Its silent twin — the same migration breaking *tests* rather than the
install — is §9 of
[06_compat-and-refactor-drift.md](06_compat-and-refactor-drift.md).

## 10. CI feedback must reach the maintainer

Inspect every check run, workflow run and commit status for the exact candidate
head, including consent and security checks. Required-check protection alone
does not cover all outcomes. A local watcher can help notice failures, but a
personal vendor-specific hook path is not an installed SciTeX guarantee.

Dev's source quality workflow and `tests/develop/test_audit.py` provide separate
audit entry points. Neither proves that a nightly job executed, an alert was
delivered, or a release passed. Keep unsuccessful and incomplete evidence
visible; follow the owning release procedure before merging or publishing.

## 11. Conflicting license metadata blocks the build

**Symptom.** ``pip install -e .`` fails with
``setuptools.errors.InvalidConfigError: License classifiers have been
superseded by license expressions``. CI's *Test* / *Tests* job aborts
before any test runs.

**Source check.**
`scitex_dev._ecosystem._release.pyproject_lint.check_orphan_license_classifier`
reports a `License :: ...` classifier as
`E5C13_orphan_license_classifier` (HIGH). Its behavioral controls are in
`tests/scitex_dev/_ecosystem/_release/test_pyproject_lint.py`. This metadata
finding is separate from actually building with the declared backend.

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

## Runtime import locations (PS-233)

PS-233 examines each source import without executing the package. An import
inside a `try` whose handler catches `ImportError` is an optional capability;
an unrelated unguarded import of the same distribution still requires a core
dependency and remains an error at its own location. The guarded location must
not be reported as unguarded merely because another file needs that package.

A `try` around a function definition does not protect imports executed later
inside that function. Imports in a handler, `else` or `finally` are likewise not
protected by that same `try`; an enclosing actual ImportError guard can still
protect them. This is source-contract evidence, not proof that an installed
wheel resolves its declared dependency graph. Preserve normal full-resolution
and fresh-wheel qualification; do not move a truly required dependency into an
extra or silence the remaining unguarded finding.
