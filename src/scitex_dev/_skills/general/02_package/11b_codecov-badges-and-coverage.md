---
description: |
  [TOPIC] CI and Codecov — badges, common gotchas, and reaching ≥90%
  [DETAILS] The README two-row badge layout (release metadata on top, build health below) and the codecov badge URL pattern; the common gotchas (upload skipped on test failure, coverage stuck at ~19% from `.[dev]`-only installs, badge stuck at "unknown", silent codecov drops); and the honest tradeoffs for reaching ≥90% coverage (per-format round-trip loaders, smoke-vs-ignore for CLI/MCP scaffolding, ignoring pure interface code). Companion to [11_ci-and-codecov.md](11_ci-and-codecov.md).
tags: [scitex-general-package-ci-codecov]
---

# Codecov — badges, gotchas, reaching ≥90%

> Parent leaf: [`11_ci-and-codecov.md`](11_ci-and-codecov.md).

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
