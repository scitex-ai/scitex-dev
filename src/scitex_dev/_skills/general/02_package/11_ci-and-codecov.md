---
description: |
  [TOPIC] CI and Codecov Setup for SciTeX Packages
  [DETAILS] Adopted 2026-05. Documents the GitHub Actions test.yml shape, codecov-action@v5 invocation, the `if: always() && matrix.python-version == 'X'` upload pattern (so coverage uploads even when tests fail), the `.[all,dev]` install line (so optional-dep loaders actually run), the canonical codecov.yml ignore patterns (_sphinx_html, _skills, _completion.py, tests, examples), the `codecov.branch: develop` line that points the unbranched badge at develop (since main is just a release-mirror), CODECOV_TOKEN secret setup (sourced from ~/.dotfiles/.../codecov.txt via 000_ACCESS_TOKENS.src), and the two-row badge layout that exposes it on README. Use when wiring coverage on a new SciTeX peer or debugging why a badge shows "unknown" / a stale number.
tags: [scitex-general-package-ci-codecov]
---

# CI and Codecov Setup

> Split-out leaves of THIS section: [badges, gotchas, reaching 90%](11b_codecov-badges-and-coverage.md) · [the mandatory audit test + config deferrals](11c_codecov-audit-test-and-config.md) · [hard cov-fail-under gate + dev-bootstrap + workflow merge](11d_codecov-gate-and-dev-bootstrap.md)

## Reference package

`scitex-io` is the canonical example. When wiring coverage on a new peer,
mirror these three files verbatim and substitute the import name:

- `.github/workflows/test.yml`
- `codecov.yml`
- README badge block (two-row layout, see below)

Do not invent a different shape — every package in the ecosystem should look
the same so a single grep across repos keeps the convention enforceable.

## test.yml workflow shape

Matrix over Python 3.10 / 3.11 / 3.12 / 3.13. Install with a fallback chain
so packages that don't declare `[all]` still build. Upload coverage exactly
once per workflow run, gated on the 3.12 row and `if: always()` so a failing
test row still ships its `coverage.xml`.

```yaml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[all,dev]" || pip install -e ".[dev]" || pip install -e .
      - name: Run tests
        run: |
          pytest --cov=src/<import_name> --cov-report=xml --cov-report=term
      - name: Upload coverage to Codecov
        if: always() && matrix.python-version == '3.12'
        uses: codecov/codecov-action@v5
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          files: ./coverage.xml
          fail_ci_if_error: false
```

The `if: always()` is the critical bit. Without it, GitHub Actions implicitly
evaluates `success()` and skips the upload whenever any prior step (including
pytest) fails — which is exactly when you most want coverage visible.

## codecov.yml

Drop this at repo root. Adjust the `<import_name>` token but keep everything
else identical across packages:

```yaml
codecov:
  require_ci_to_pass: false
  # Treat develop as the de-facto default branch — main is a stable
  # release mirror that only fast-forwards from develop, so develop
  # is where coverage uploads land. This makes the unbranched badge
  # endpoint (/graph/badge.svg) follow develop's value.
  branch: develop

coverage:
  status:
    project:
      default:
        target: auto
        threshold: 1%
    patch:
      default:
        target: 80%

ignore:
  - "src/<import_name>/_sphinx_html/**"
  - "src/<import_name>/_skills/**"
  - "src/<import_name>/_completion.py"
  - "src/<import_name>/_cli/_completion.py"
  - "tests/**"
  - "examples/**"

comment:
  layout: "diff, files"
  require_changes: true
```

Rationale:

- `codecov.branch: develop` — the codecov page's headline number and
  the unbranched `/graph/badge.svg` follow develop. Without this, the
  badge points at `main` (the release-mirror branch) and shows the
  stale number from the last release-cut while develop has long since
  moved on. Every SciTeX peer uses this.
- `_sphinx_html/` is generated HTML; never covered.
- `_skills/` is markdown documentation; not executable.
- `_completion.py` (and `_cli/_completion.py`) are shell-completion shims —
  pure boilerplate, no real logic to test.
- `tests/` and `examples/` shouldn't count toward their own coverage.

### README badge URL

For belt-and-suspenders robustness against any codecov-side config
drift, the README badge can also pin develop explicitly:

```markdown
[![Coverage (develop)](https://codecov.io/gh/<org>/<repo>/branch/develop/graph/badge.svg)](https://codecov.io/gh/<org>/<repo>/branch/develop)
```

This always renders develop's number regardless of dashboard
settings. Recommended in addition to `codecov.branch: develop`.

## CODECOV_TOKEN secret

Three steps, in order:

1. **Token file** lives at
   `~/.dotfiles/src/.bash.d/secrets/access_tokens/codecov.txt`
   (one line, the upload token from codecov.io account settings).

2. **Shell export** — add a `CODECOV_TOKEN_PATH` block to
   `~/.dotfiles/src/.bash.d/secrets/000_ACCESS_TOKENS.src`, mirroring the
   existing `GITHUB_TOKEN` / `HUGGINGFACE_TOKEN` / `SLACK_TOKEN` entries
   (load-if-exists guard, then `export CODECOV_TOKEN="$(cat …)"`). This makes
   `gh secret set` work from any shell without copy-paste.

3. **Repo secret**:
   ```bash
   gh -R <owner>/<pkg> secret set CODECOV_TOKEN < \
     ~/.dotfiles/src/.bash.d/secrets/access_tokens/codecov.txt
   ```

Note: codecov-action@v5 supports tokenless uploads for public repos, but the
explicit token is more reliable for badge ingestion (the first tokenless
upload on a brand-new repo sometimes lags before the badge resolves).

## Badges, common gotchas, and reaching ≥ 90%

> Moved to its own leaf: [11b_codecov-badges-and-coverage.md](11b_codecov-badges-and-coverage.md) — the README two-row badge layout + codecov badge URL, the common gotchas (upload skipped on failure, coverage stuck at ~19%, badge "unknown", silent drops), and the honest tradeoffs for reaching ≥ 90% coverage.

## The mandatory audit test and config deferrals

> Moved to its own leaf: [11c_codecov-audit-test-and-config.md](11c_codecov-audit-test-and-config.md) — the mandatory `tests/develop/test_audit.py` running `audit-all`, why `skip_rules=` is not for muffling real violations, deferring a rule to a migration campaign via `audit.skip-rules`, and the `.gitignore` exception that tracks `.scitex/dev/config.yaml`.

## Hard coverage gate, dev-bootstrap deps, and workflow merge

> Moved to its own leaf: [11d_codecov-gate-and-dev-bootstrap.md](11d_codecov-gate-and-dev-bootstrap.md) — the optional `--cov-fail-under=90` guard, the rule that `[dev]` must install marker-providing packages (pytest-asyncio, fastmcp), the test-file `pytest.importorskip` requirement, merging `Test` + `Install Test` into one workflow, and `tests/integration/<mirror>/` placement for `_real.py` tests.

## Related skills

- `02_package/07_github-actions.md` — workflow conventions, matrix shape,
  install-test workflow.
- `02_package/08_quality.md` — overall package quality bar.
- `01_ecosystem/02_dependency-and-version-pinning.md` — the `[dev]` extras
  completeness rule that makes `.[all,dev]` reliable.
- `03_interface/01_python-api/04_lazy-imports-and-optional-deps.md` —
  `try_import_optional` canonical pattern (PA-302); pairs with
  `pytest.importorskip` on the test side (PA-303).
