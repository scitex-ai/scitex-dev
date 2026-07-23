---
description: |
  [TOPIC] No mocks — the worked example and campaign-produced patterns
  [DETAILS] The concrete replacement patterns from the PA-306 no-mock conversion campaign: the `scitex_dev._creds._rotate` worked example (production refactor to accept collaborators as keyword params + test refactor that writes a real `gh` shell shim into `tmp_path/bin` and prepends `$PATH`), the two reusable fixtures the campaign distilled (`subprocess_shim`, `env_save_restore`), and the rule to instantiate real production dataclasses instead of `SimpleNamespace`-as-config. Companion to [12_no-mocks.md](12_no-mocks.md).
tags: [scitex-general-package-no-mocks]
---

# No mocks — worked example and campaign patterns

> Parent leaf: [`12_no-mocks.md`](12_no-mocks.md). This leaf carries the concrete replacement patterns; the rule, the why, and the replacement menu live in the parent.

## Worked example — `scitex_dev._creds._rotate`

The original test patched `_detect_repo_for_package`'s module-level
collaborators (`get_local_path`, `ECOSYSTEM`) via `monkeypatch.setattr`,
and patched `subprocess.check_output` via `unittest.mock.patch`.

**Production refactor** — accept the collaborators as keyword
parameters, default to the module globals:

```python
# src/scitex_dev/_creds/_rotate.py
def _detect_repo_for_package(
    name: str,
    *,
    ecosystem: dict | None = None,
    local_path_lookup=None,
) -> str | None:
    if local_path_lookup is None:
        local_path_lookup = get_local_path
    if ecosystem is None:
        ecosystem = ECOSYSTEM
    local = local_path_lookup(name)
    ...
    info = ecosystem.get(name) or {}
    ...
```

**Test refactor** — pass a real fake registry dict and a real
`local_path_lookup` callable; for the subprocess call, write a real
shell shim into `tmp_path/bin/gh` and prepend it to `$PATH`:

```python
def _install_gh_shim(bin_dir: Path, *, remote_sha: str | None = None) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    log = bin_dir / "calls.log"
    log.write_text("")
    sha = remote_sha or ""
    script = f"""#!/usr/bin/env bash
verb="$1 $2"
case "$verb" in
  "variable get") echo "var_get" >> "{log}"; echo "{sha}"; exit 0 ;;
  "secret set")   echo "secret_set" >> "{log}"; exit 0 ;;
  ...
esac
"""
    gh = bin_dir / "gh"
    gh.write_text(script)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return log
```

This is a real subprocess. It exercises the real `subprocess.check_output`
call in production. If we rename the `gh` invocation, the test fails. If
GitHub's `gh` changes its argument shape, an integration test against the
real binary will catch it. The mock-based version caught neither.

The full refactor is visible in commit history under `_creds/_rotate.py`
and `tests/scitex_dev/_creds/test__rotate.py` from 2026-05-14.

## Shared fixtures the campaign produced

The PA-306 conversion campaign distilled two reusable fixtures that
replace the most common mock idioms. Lift them into `conftest.py`
rather than re-implementing per file:

- **`subprocess_shim`** — writes a real fake binary into
  `tmp_path/bin/<name>`, prepends `$PATH`, returns a calls-log path.
  Replaces `unittest.mock.patch("subprocess.check_output")` and the
  whole family of "I just want to assert we called `gh variable get`"
  tests. The shim is a real shell script; it exercises the real
  `subprocess` codepath end-to-end and fails honestly if the
  production call shape changes.
- **`env_save_restore`** — `yield`-based fixture that snapshots and
  restores `os.environ` mutations across a test. Replaces every
  `monkeypatch.setenv(...)` pattern.

## Real production dataclasses, not `SimpleNamespace`-as-config

A `MagicMock`-shaped or `types.SimpleNamespace`-shaped config object
passed to production code is a mock under a different name: it answers
every attribute lookup the test author thought to write, and silently
diverges from the production dataclass schema. **Always instantiate the
real production dataclass** (`AgentConfig(name="...", ...)` etc.). If
the dataclass has many required fields, give them sensible defaults
upstream rather than dodging it with `SimpleNamespace`. The
field-rename-breaks-tests property is what we want.
