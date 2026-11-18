# JavaScript callee diagnostics

The source controls in `.github/tests/test_dev_ci_adapters.py` evaluate the
reviewed public callee contract using Node. The actual-callee control adds three
constant stderr lines around the unchanged contract and invocation:

| Captured stage | Positive observation |
| --- | --- |
| `javascript-entered` | JavaScript reached the first statement. |
| `contract-loaded` | Synchronous evaluation reached the statement after the contract. |
| `invocation-evaluated` | Synchronous evaluation reached the statement after the invocation. |

The last marker does not establish asynchronous completion, a successful process
exit or passing assertions. A JavaScript syntax error can prevent every marker,
including the first, because parsing precedes evaluation.

On timeout, `_dev_ci_node_probe.py` extracts only exact, complete, recognized
marker lines from the first 512 already captured stderr bytes (or characters for
a text capture). The exception note contains constant stage labels, never
arbitrary captured text. The original `TimeoutExpired` output remains available
to its caller. Missing markers are inconclusive: capture may be incomplete or
truncated. These labels are diagnostic observations, not authenticated evidence
or a root-cause verdict.

The four-second deadline, reviewed fixture, protocol assertions, process cleanup
and existing direct-child observations remain in effect. The controls perform no
warmup or automatic retry. A new passing diagnostic test does not qualify an
older failed CI run, a package release or a hosted deployment.

Run the real source controls with Node and PyYAML available:

```sh
python -m unittest discover -s .github/tests -p 'test_dev_ci*.py' -v
```
