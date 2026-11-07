---
description: |
  [TOPIC] Test quality and fixture isolation
  [DETAILS] Use current Dev auditors and linter commands, retain discriminating cases and observations, isolate real collaborators and runtime settings, and clean up owned fixture resources. Distinguish focused checks, full native validation and service acceptance; do not hide failures or weaken gates.
tags: [scitex-general-development-tq-migration]
---

# Test quality and fixture isolation

Use this guide when a package's Python API audit reports PA-306/PA-307 or its
linter reports NM/TQ findings. Read the actual findings in the selected checkout;
a historical package count or migration report does not establish current state.

## 1. Establish the source and failure

Use the installed umbrella route when available:

```bash
scitex dev ecosystem audit-python-apis scitex-dev --path . --json
scitex dev linter validate-files tests/ --json
```

Substitute the owning distribution and its actual checkout. Standalone bootstrap
uses `scitex-dev ecosystem ...` and `scitex-dev linter ...`. `scitex-linter` is a
retired standalone package, not the recommended command. Inspect installed help
before applying instructions to another version.

Keep the original failing output and identify the behavior at risk. A zero
finding count is structural evidence, not proof that a feature works. The
forbidden `--new-only` mode must not be used to downgrade existing errors.

## 2. Exercise the real boundary

Prefer an owned Git repository, temporary filesystem, in-process server or actual
local subprocess. Keep dependency-injection seams explicit. An injected test
collaborator or protocol fixture can qualify its stated local contract; it does
not establish that a remote provider, credential, scheduler or deployment works.
Do not manufacture native acceptance by making a shell shim print success.

The NM rules reject mock-library imports, mock fixture parameters and mock
symbol use. Their definitions are in `linter/_rules/_no_mocks.py`. Replacing a
mock with another imitation is not sufficient evidence of correct behavior.

## 3. Preserve cases and observations

The TQ rules are defined in `linter/_rules/_test_quality.py` and checked by
`linter/_checks/_test_quality.py`. They cover meaningful assertions, descriptive
names, Arrange/Act/Assert phases, fixture lifetime, parameterized branches and
assertion structure. Inspect the implemented rule rather than inferring a
waiver from this page.

Keep every discriminating input, expected error, returned value and state check.
One assertion may compare a complete tuple of observations from one operation;
do not discard checks merely to reduce the assertion count. Put shared setup in
fixtures and retain the original cases when splitting tests. Increasing the
number of test functions is not itself an improvement.

An assertion that a function is callable, or a flag set unconditionally by the
test, does not replace validation of the operation's actual result. A genuine
unavailable dependency remains unavailable; do not turn it into a fabricated
success or add a skip to make the suite green.

## 4. Own configuration and teardown

Use an owned HOME, runtime directory and working directory when testing defaults
or file mutations. Place the active interpreter first on PATH for existing
subprocess consumers and prefer `sys.executable` in new Python subprocess calls.
Do not inherit an operator's terminal, service or credential preferences and
then mistake them for library defaults. Preserve the failed observation and
state the environment used for the clean check.

Register cleanup with a fixture's `yield`/`finally` or `request.addfinalizer`.
Remove only resources that fixture created, including files created for unusual
filename tests. Keep raw-byte, newline and Unicode cases: the test owner should
handle teardown with the same filesystem API that created the resource. Do not
assume a CI runner implemented in another runtime can remove every valid name.
Verify that teardown leaves no unsupported names in the owned test tree.

For example, the source test
`scitex-logging/tests/scitex_logging/_output/test__inventory.py` exercises seven
filename forms, including an undecodable byte. Its Git inventory and auditor
assertions are useful coverage; removing that case or weakening its assertion
would hide the behavior rather than repair fixture lifetime.

Runner cleanup is a separate operational concern. Diagnose the actual failed
path and ownership before touching it. Preserve positively identified stale
artifacts outside the runner's temporary tree when recovery needs quarantine.
An unprivileged process listing may not reveal a service worker; inability to
inspect a process is not evidence that a runner is idle. Do not recursively
change permissions or move a current job's whole environment on that assumption.

## Validation and reporting

Run the package's declared full test profile and mandatory audit after focused
controls. Some Dev-integrated projects deliberately reject a partial session
when their audit gate was not collected; retain that exit status. Selected test
passes are not a complete green suite.

Preserve exact-head CI failures, including failures outside the changed files.
Do not instruct another maintainer to ignore a red CI flag. Keep deadlines,
coverage thresholds, admitted profiles and original test expectations intact.
Report what passed, what failed or was skipped, and which real services remain
unverified. Source, installed artifacts and live adoption are separate scopes.

Related: [no mocks](../02_package/12_no-mocks.md),
[test quality](../02_package/13_test-quality.md),
[test layout](../02_package/06_project-structure-tests.md), and
[documentation drift](22_documentation-drift.md).
