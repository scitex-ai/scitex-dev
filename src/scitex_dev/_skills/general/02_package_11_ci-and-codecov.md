---
description: |
  [TOPIC] CI and Codecov Setup for SciTeX Packages
  [DETAILS] Adopted 2026-05. Documents the GitHub Actions test.yml shape, codecov-action@v5 invocation, the `if: always() && matrix.python-version == 'X'` upload pattern (so coverage uploads even when tests fail), the `.[all,dev]` install line (so optional-dep loaders actually run), the canonical codecov.yml ignore patterns (_sphinx_html, _skills, _completion.py, tests, examples), the `codecov.branch: develop` line that points the unbranched badge at develop (since main is just a release-mirror), CODECOV_TOKEN secret setup (sourced from ~/.dotfiles/.../codecov.txt via 000_ACCESS_TOKENS.src), and the two-row badge layout that exposes it on README. Use when wiring coverage on a new SciTeX peer or debugging why a badge shows "unknown" / a stale number.
tags: [scitex-general-package-ci-codecov]
---

# CI and Codecov Setup

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

## Common gotchas

- **Upload skipped on test failure.** Add `if: always() && matrix.python-version == '3.12'`
  to the codecov step. Pytest writes `coverage.xml` even when tests fail; the
  upload step just needs to opt back in to running on failure.
- **Coverage stuck at ~19%.** CI is installing only `.[dev]`, so loaders
  guarded by `pytest.importorskip("h5py")` etc. get skipped. Install
  `.[all,dev]` to exercise the full scientific stack.
- **Badge shows "unknown" forever.** Repo not activated on codecov.io and/or
  `CODECOV_TOKEN` missing. Set the secret; the first successful upload
  auto-activates the repo.
- **Codecov drops uploads silently.** `fail_ci_if_error: false` swallows the
  error so CI stays green. Check the workflow step logs (search for
  "codecov") for the real cause — usually a missing token or a malformed
  `coverage.xml` path.

## Badge in README

Two-row layout. Top row = release metadata, bottom row = build health:

```markdown
[![PyPI](https://img.shields.io/pypi/v/<pkg>.svg)](https://pypi.org/project/<pkg>/)
[![Python](https://img.shields.io/pypi/pyversions/<pkg>.svg)](https://pypi.org/project/<pkg>/)
[![Read the Docs](https://readthedocs.org/projects/<pkg>/badge/?version=latest)](https://<pkg>.readthedocs.io/)

[![Tests](https://github.com/<owner>/<pkg>/actions/workflows/test.yml/badge.svg)](https://github.com/<owner>/<pkg>/actions/workflows/test.yml)
[![Install Test](https://github.com/<owner>/<pkg>/actions/workflows/install-test.yml/badge.svg)](https://github.com/<owner>/<pkg>/actions/workflows/install-test.yml)
[![codecov](https://codecov.io/gh/<owner>/<pkg>/graph/badge.svg)](https://codecov.io/gh/<owner>/<pkg>)
```

Codecov badge URL pattern: `https://codecov.io/gh/<owner>/<pkg>/graph/badge.svg`.

## Reaching ≥ 90% coverage

Honest tradeoffs — there is no shortcut:

- **Per-format loaders** (`_save_modules/`, `_load_modules/`) need real
  round-trip tests. One test per format: save → load → assert equal. This is
  the bulk of the coverage work for I/O-heavy packages.
- **CLI / MCP scaffolding** — either write smoke tests (invoke each
  subcommand with `--help` and assert exit 0) OR add to `codecov.yml` ignore
  list. Judgment call per package; smoke tests are usually cheap.
- **Pure interface code** (shell-completion shims, generated scaffolding,
  `__main__.py` thunks) — ignore in `codecov.yml`. These are not testable
  units.
- 90% is achievable **only** with real tests for the format loaders.
  Ignoring everything but the core to inflate the number is dishonest and
  will rot when someone later removes the ignores.

## Related skills

- `02_package_07_github-actions.md` — workflow conventions, matrix shape,
  install-test workflow.
- `02_package_08_quality.md` — overall package quality bar.
- `01_ecosystem_02_dependency-and-version-pinning.md` — the `[dev]` extras
  completeness rule that makes `.[all,dev]` reliable.
