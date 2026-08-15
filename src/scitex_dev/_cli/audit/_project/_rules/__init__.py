"""Project-structure audit rule corpus.

The rule LITERALS live in the `_s*.py` siblings; this module is the
ASSEMBLY: it builds `RULES` from them, merges every co-located
`_check_*` rule set, and only THEN applies the severity/slug tables.

That ordering is load-bearing, and the tables, the merge loops and the
apply statement are kept together in this ONE file on purpose.
`_patch` used to run before the co-located merges, which made
`_SEVERITY_OVERRIDES` and `_SLUGS` a SILENT NO-OP for 31 rules — adding
`"PS-220": "E"` to the table did nothing, with no error and no warning.
A severity table that silently ignores entries is itself a gate that
cannot fail. `test__registry_severity_overrides.py` pins the invariant by
reading THIS file's source text and re-executing it with an injected
override, so splitting the three parts into separate modules would
disable the regression test that guards them.

Split out of `_registry.py` (1286 lines, cap 512); see
GITIGNORED/REFACTORING.md. Pure move, no behaviour change.
"""

from __future__ import annotations

from ._rule import Rule
from ._s1_layout import RULES_S1_LAYOUT
from ._s1_readme_extended import RULES_S1_README_EXTENDED
from ._s2_src_tests import RULES_S2_SRC_TESTS
from ._s3_tests_examples import RULES_S3_TESTS_EXAMPLES
from ._s4_docs import RULES_S4_DOCS

RULES: dict[str, Rule] = {
    r.code: r
    for r in [
        *RULES_S1_LAYOUT,
        *RULES_S1_README_EXTENDED,
        *RULES_S2_SRC_TESTS,
        *RULES_S3_TESTS_EXAMPLES,
        *RULES_S4_DOCS,
    ]
}

# Severity escalation table.
#
# Per 2026-05-06 directive: every rule that ships a concrete spec defaults to
# E (error → fails CI). Demote back to W only after a documented false
# positive lands on develop. New rules MAY start at W during their initial
# bake-in, but the bar for staying W is "active false-positive history",
# not "we haven't promoted it yet".
#
# E (error) — fails CI; the rule is well-tested and the fix is mechanical.
# W (warn)  — prints, doesn't fail; for rules with active false-positive
#             history that haven't been demoted yet.
# I (info)  — printed only with --severity info; never fails. Use for
#             purely advisory categorizations (no actionable violation).
_SEVERITY_OVERRIDES: dict[str, str] = {
    # Structural — must hold for any package
    "PS-101": "E",  # missing pyproject.toml
    "PS-102": "E",  # forbidden top-level dir (logs/, mgmt/, ...)
    "PS-103": "E",  # top-level junk file
    "PS-104": "E",  # uses .playground/
    "PS-105": "E",  # console_scripts present but no __main__.py
    # README content — every public package follows the convention
    "PS-106": "E",
    "PS-107": "E",
    "PS-108": "E",
    "PS-108b": "E",
    "PS-109": "E",
    "PS-110": "E",
    "PS-111": "E",
    "PS-112": "E",
    "PS-113": "E",
    "PS-114": "E",
    "PS-115": "E",
    "PS-116": "E",
    "PS-117": "E",
    "PS-118": "E",
    "PS-119": "E",
    # PS-120 retired 2026-05-18 (umbrella one-liner content rule).
    "PS-123": "E",
    "PS-129": "E",
    "PS-130": "E",
    "PS-131": "E",
    "PS-132": "E",
    # Sphinx / RTD bundle
    "PS-121": "E",
    "PS-122": "E",
    "PS-124": "E",
    "PS-125": "E",
    "PS-126": "E",
    "PS-127": "E",
    "PS-128": "E",
    # Community files — every public package needs them
    "PS-133": "E",  # CLA.md
    "PS-134": "E",  # CHANGELOG.md
    "PS-135": "E",  # CONTRIBUTING.md
    "PS-136": "E",  # examples/
    "PS-137": "E",  # README.md
    "PS-138": "E",  # LICENSE present
    "PS-138b": "E",  # LICENSE content matches SPDX (no stub)
    "PS-139": "E",  # pyproject.toml depends on scitex umbrella (anti-pattern)
    "PS-140": "E",  # missing/stale tests/integration/test_cross_package_imports.py
    "PS-141": "E",  # README missing `## Demo` with visual content
    "PS-142": "E",  # README missing `## Architecture` with diagram/tree
    "PS-145": "W",  # cross-package state read (bake-in: warn first)
    "PS-146": "E",  # pip-install side-effect (clear violation)
    "PS-147": "W",  # eval-form shell completion (bake-in: warn first)
    "PS-152": "W",  # README split Problem/Solution headings (warn)
    "PS-153": "W",  # README architecture file-tree, no mermaid (warn)
    "PS-154": "W",  # README installation not canonical (warn)
    "PS-155": "I",  # README badge row not two centered rows (info)
    "PS-156": "I",  # examples/ has .py but zero .ipynb (info)
    "PS-157": "W",  # codecov badge URL unbranched (warn)
    "PS-158": "I",  # RTD badge uses readthedocs.org baked label (info)
    "PS-159": "W",  # README figure/table numbering broken (warn)
    "PS-160": "W",  # README figure/table missing caption (warn)
    "PS-161": "W",  # codecov.yml coverage target below 90 (warn)
    "PS-162": "W",  # README missing Codecov badge (warn)
    "PS-163": "W",  # README missing Read-the-Docs badge (warn)
    "PS-150": "W",  # [dev] missing scitex-dev pin — audit gate silently skips
    "PS-151": "W",  # scitex-dev pin floor < known-good (rule corpus drift)
    "PS-164": "W",  # workflow naming/structure (warn-only during adoption)
    # src ↔ tests mirror — load-bearing for CI confidence
    "PS-201": "E",
    "PS-202": "E",
    "PS-203": "E",
    "PS-204": "E",
    "PS-205": "E",
    "PS-206": "E",  # placeholder-only test (no `def test_*` / `class Test*` at all)
    "PS-206b": "W",  # has `def test_*` but body has no assertion (import-smoke only)
    "PS-207": "E",  # empty test directory
    "PS-210": "E",  # [dev] extras incomplete
    "PS-211": "W",  # tests/smoke/ layer missing — W during ecosystem adoption
    "PS-212": "W",  # tests/e2e/ layer missing  — W during ecosystem adoption
    "PS-301": "E",  # top-level htmlcov/
    "PS-302": "E",  # unrecognized tests/ subdir
    "PS-303": "E",  # examples/<n>.py without tests/examples/test_<n>.py
    "PS-401": "E",  # docs/to_claude/ tracked
    "PS-402": "E",  # top-level assets/
    "PS-501": "E",  # examples missing @stx.session
    "PS-502": "E",  # empty examples/<n>_out/
    "PS-503": "E",  # examples/<n>_out/ missing FINISHED_SUCCESS/<id>/
    "PS-504": "E",  # .ipynb has no committed cell outputs
    "PS-505": "E",  # .ipynb test does not nbconvert / nbval
    "PS-506": "E",  # .ipynb missing %matplotlib inline
    "PS-507": "E",  # .ipynb missing plt.show()
    "PS-508": "E",  # .ipynb has warning output in committed cells
}

# Human-readable kebab-case slugs. Surfaced inline in audit output as
# `[CODE §X slug]` so reviewers can read intent without cross-referencing
# rule numbers. Backfilled in batches; missing entries render in the old
# `[CODE §X]` form (no breakage). New rules SHOULD include a slug from
# definition.
_SLUGS: dict[str, str] = {
    # §1 — top-level layout already slugged at definition (PS-101–PS-103)
    "PS-104": "uses-playground-dir",
    "PS-105": "main-py-missing",
    # README structure
    "PS-106": "readme-missing-coverage-badge",
    "PS-107": "readme-missing-h2-sections",
    # PS-108 / PS-108b detect flat-package-layout patterns in src/, NOT
    # README badges. (The badge-shaped slugs that used to sit here
    # described long-retired README rules and confused every reader.)
    "PS-108": "src-prefix-cluster-mess",
    "PS-108b": "src-flat-py-files-over-threshold",
    "PS-109": "readme-missing-pypi-version-badge",
    "PS-110": "readme-missing-four-freedoms",
    "PS-111": "readme-personal-email",
    "PS-112": "readme-missing-logo",
    "PS-113": "readme-banned-emoji",
    "PS-114": "readme-banned-marketing",
    "PS-115": "readme-missing-architecture",
    "PS-116": "readme-banned-buzzword",
    "PS-117": "readme-missing-quickstart",
    "PS-118": "readme-missing-installation",
    "PS-119": "readme-missing-part-of-scitex",
    # PS-120 retired 2026-05-18.
    "PS-123": "readme-banned-future-claim",
    "PS-129": "readme-banned-trademark-symbol",
    "PS-130": "readme-missing-related-projects",
    "PS-131": "readme-missing-citation",
    "PS-132": "readme-missing-roadmap",
    # Sphinx / RTD
    "PS-121": "rtd-onboarding-missing",
    "PS-122": "rtd-config-missing",
    "PS-124": "sphinx-conf-missing",
    "PS-125": "sphinx-makefile-missing",
    "PS-126": "sphinx-extensions-bad",
    "PS-127": "sphinx-theme-bad",
    "PS-128": "sphinx-build-broken",
    # Community files
    "PS-133": "missing-cla",
    "PS-134": "missing-changelog",
    "PS-135": "missing-contributing",
    "PS-136": "missing-examples-dir",
    "PS-137": "missing-readme",
    "PS-138": "missing-license",
    "PS-138b": "license-stub-mismatched",
    "PS-139": "pyproject-depends-on-umbrella",
    "PS-140": "cross-package-imports-test-missing",
    "PS-141": "readme-missing-demo",
    "PS-142": "readme-missing-architecture-diagram",
    "PS-143": "readme-missing-badge-row",
    "PS-144": "readme-missing-pypi-status",
    "PS-152": "readme-split-problem-solution",
    "PS-153": "readme-architecture-filetree-not-mermaid",
    "PS-154": "readme-installation-not-canonical",
    "PS-155": "readme-badge-row-not-two-rows",
    "PS-156": "examples-no-ipynb",
    "PS-157": "readme-codecov-badge-unbranched",
    "PS-158": "readme-rtd-badge-baked-label",
    "PS-159": "readme-figures-tables-numbering",
    "PS-160": "readme-figures-tables-missing-caption",
    "PS-161": "readme-codecov-coverage-target-too-low",
    "PS-162": "readme-missing-codecov-badge",
    "PS-163": "readme-missing-rtd-badge",
    "PS-150": "dev-extras-missing-scitex-dev",
    "PS-151": "dev-extras-scitex-dev-floor-too-old",
    # §2 src↔tests already slugged at definition (PS-201–PS-205)
    "PS-206": "test-placeholder-only",
    "PS-206b": "test-import-smoke-only",
    "PS-207": "empty-test-dir",
    "PS-210": "dev-extras-incomplete",
    # §3 docs / examples
    "PS-301": "top-level-htmlcov",
    "PS-302": "tests-unknown-subdir",
    "PS-303": "example-without-test",
    # §4 docs/to_claude
    "PS-401": "docs-to-claude-tracked",
    "PS-402": "top-level-assets",
    # §5 examples + notebooks (PS-503 already slugged)
    "PS-501": "example-without-stx-session",
    "PS-502": "examples-out-empty",
    "PS-504": "ipynb-no-cell-outputs",
    "PS-505": "ipynb-test-not-nbconvert",
    "PS-506": "ipynb-missing-matplotlib-inline",
    "PS-507": "ipynb-missing-plt-show",
    "PS-508": "ipynb-warning-in-output",
}


# Apply the overrides — replace each tagged Rule with a promoted copy that
# carries both the (optional) severity override and the (optional) slug.
def _patch(rule: Rule) -> Rule:
    sev = _SEVERITY_OVERRIDES.get(rule.code, rule.severity)
    slug = rule.slug or _SLUGS.get(rule.code, "")
    if sev == rule.severity and slug == rule.slug:
        return rule
    return Rule(rule.code, rule.section, rule.message, sev, slug)


# NOTE — `_patch` is applied ONCE, at the BOTTOM of this module, AFTER every
# co-located/sidecar rule set below has been merged into RULES.
#
# It used to run HERE, before those merges, which made `_SEVERITY_OVERRIDES`
# and `_SLUGS` a SILENT NO-OP for every rule registered after this point
# (EXTRA_RULES, HOOK_RULES, URL_DEP_RULES, SKILLS/DOCTOR/VERSION,
# PRINT_FORBIDDEN_RULES, ALL_CLOSURE_RULES — 31 rules as of 2026-07-22).
# Adding e.g. `"PS-220": "E"` to the override table did nothing at all, with
# no error and no warning: a severity table that silently ignores entries is
# itself a gate that cannot fail. Keep the application at the bottom, and see
# `test__registry_severity_overrides.py` for the regression that pins it.

# hook-bypass: line-limit
# Sidecar rule registration — see ._extra_rules / GITIGNORED/REFACTORING.md.
from .._extra_rules import EXTRA_RULES as _EXTRA_RULES  # noqa: E402

for _c, _sec, _msg, _sev, _slug in _EXTRA_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# Co-located rule registration. `_extra_rules.py` exists because THIS file blew
# the 512-line cap; it has now blown the cap itself. Rather than grow a third
# generation of sidecar, new rules ship in the shape `_extra_rules.py`'s own
# docstring names as the target architecture — "each rule co-located with its
# check module" — and are merged here on the same terms.
from .._check_precommit_hooks import HOOK_RULES as _HOOK_RULES  # noqa: E402

for _c, _sec, _msg, _sev, _slug in _HOOK_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# hook-bypass: line-limit
# PS-216 — direct-URL/VCS deps in publishable metadata (co-located rule,
# merged on the same terms as HOOK_RULES / EXTRA_RULES).
from .._check_no_url_deps import URL_DEP_RULES as _URL_DEP_RULES  # noqa: E402

for _c, _sec, _msg, _sev, _slug in _URL_DEP_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# hook-bypass: line-limit
# PS-217 — skills CLI federation; PS-218/PS-219 — CLI-normalization
# doctor/health + version-flag conformance (co-located rules, merged on the
# same terms as HOOK_RULES / URL_DEP_RULES).
from .._check_skills_federation import (  # noqa: E402
    SKILLS_FEDERATION_RULES as _SKILLS_FEDERATION_RULES,
)
from .._check_doctor_health_naming import (  # noqa: E402
    DOCTOR_HEALTH_RULES as _DOCTOR_HEALTH_RULES,
)
from .._check_version_flag import VERSION_FLAG_RULES as _VERSION_FLAG_RULES  # noqa: E402

for _c, _sec, _msg, _sev, _slug in (
    *_SKILLS_FEDERATION_RULES,
    *_DOCTOR_HEALTH_RULES,
    *_VERSION_FLAG_RULES,
):
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# hook-bypass: line-limit
# PS-220 — `print(...)` in scitex source (enforce scitex-logging). Co-located
# rule, merged on the same terms as HOOK_RULES / URL_DEP_RULES / VERSION_FLAG.
from .._check_no_print import PRINT_FORBIDDEN_RULES as _PRINT_FORBIDDEN_RULES  # noqa: E402

for _c, _sec, _msg, _sev, _slug in _PRINT_FORBIDDEN_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# PS-221 — [all]-closure on public optional-dependency extras (co-located
# rule, merged on the same terms as URL_DEP_RULES / HOOK_RULES).
from .._check_extras_all_closure import (  # noqa: E402
    ALL_CLOSURE_RULES as _ALL_CLOSURE_RULES,
)

for _c, _sec, _msg, _sev, _slug in _ALL_CLOSURE_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# PS-225 — extra NAMES restricted to {all, dev, docs} (co-located rule,
# merged on the same terms as ALL_CLOSURE_RULES). Severity W lives in the
# tuple for the rollout; see the module docstring and ADR-0005.
from .._check_extras_allowlist import (  # noqa: E402
    EXTRAS_ALLOWLIST_RULES as _EXTRAS_ALLOWLIST_RULES,
)

for _c, _sec, _msg, _sev, _slug in _EXTRAS_ALLOWLIST_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# PS-222 — `.scitex/<pkg-short>/` config-layout convention (co-located rule,
# merged on the same terms as ALL_CLOSURE_RULES / PRINT_FORBIDDEN_RULES).
# Severity W lives in the tuple, NOT in `_SEVERITY_OVERRIDES` — see the note
# beside `_patch`: an override for a co-located rule is a silent no-op.
from .._check_config_layout import (  # noqa: E402
    CONFIG_LAYOUT_RULES as _CONFIG_LAYOUT_RULES,
)

for _c, _sec, _msg, _sev, _slug in _CONFIG_LAYOUT_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# PS-223 — non-`runtime/` logs-path string literal in package source
# (co-located rule, merged on the same terms as CONFIG_LAYOUT_RULES).
# Severity W lives in the tuple, NOT in `_SEVERITY_OVERRIDES` — see the note
# beside `_patch`: an override for a co-located rule is a silent no-op.
from .._check_logs_path import LOGS_PATH_RULES as _LOGS_PATH_RULES  # noqa: E402

for _c, _sec, _msg, _sev, _slug in _LOGS_PATH_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# hook-bypass: line-limit
# PS-224 — CI runner destination must exist in the scitex-dev machine
# registry (co-located rule, merged on the same terms as LOGS_PATH_RULES).
# Severity **E** lives in the tuple, NOT in `_SEVERITY_OVERRIDES` — see the
# note beside `_patch`: an override for a co-located rule is a silent no-op,
# and a rule that ships at E precisely so it CAN fail a build must never have
# its severity routed through a table that would drop it.
from .._check_runner_destinations import (  # noqa: E402
    RUNNER_DESTINATION_RULES as _RUNNER_DESTINATION_RULES,
)

for _c, _sec, _msg, _sev, _slug in _RUNNER_DESTINATION_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# hook-bypass: line-limit
# PS-226..PS-229 — the fleet-wide JobSpec declaration convention (co-located
# rule set, merged on the same terms as RUNNER_DESTINATION_RULES). Severities
# live in the tuples, NOT in `_SEVERITY_OVERRIDES` — see the note beside
# `_patch`: an override for a co-located rule is a silent no-op, and PS-226's
# whole purpose is to FAIL, so its E must not be routed through a table that
# would drop it.
from .._check_job_naming import JOB_NAMING_RULES as _JOB_NAMING_RULES  # noqa: E402

for _c, _sec, _msg, _sev, _slug in _JOB_NAMING_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)

# hook-bypass: line-limit
# PS-230 — retired role vocabulary in package PROSE (co-located rule set,
# merged on the same terms as JOB_NAMING_RULES). PS-226..229 above make job
# NAMES and KINDS mechanical; PS-230 closes the other half of the same
# operator decision — the WORDS — which the naming skill itself flagged as
# "convention until an auditor rule exists". Severity W lives in the tuple,
# NOT in `_SEVERITY_OVERRIDES`: an override for a co-located rule is a
# silent no-op (see the note beside `_patch`).
from .._check_naming_vocabulary import (  # noqa: E402
    NAMING_VOCABULARY_RULES as _NAMING_VOCABULARY_RULES,
)

for _c, _sec, _msg, _sev, _slug in _NAMING_VOCABULARY_RULES:
    RULES[_c] = Rule(_c, _sec, _msg, _sev, _slug)


# hook-bypass: line-limit
# ---------------------------------------------------------------------------
# Severity/slug overrides are applied LAST, so the table is honest for EVERY
# registered rule — the ones defined literally in `RULES` above AND every
# co-located/sidecar set merged in between. See the note beside `_patch`.
# ---------------------------------------------------------------------------
RULES = {code: _patch(rule) for code, rule in RULES.items()}

__all__ = ["Rule", "RULES"]

# EOF
