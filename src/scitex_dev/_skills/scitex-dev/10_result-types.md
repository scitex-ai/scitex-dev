---
description: |
  [TOPIC] Result types
  [DETAILS] Structured Result envelopes, error codes, exception classification, opt-in return wrapping and side-effect declarations. Examples use current public exports and actual serialized fields.
tags: [scitex-dev-result-types]
---

# Result types

## Result

`Result` carries output and metadata for Python, CLI and MCP consumers:

```python
import json
from scitex_dev import Result

result = Result(success=True, data={"rows": 42}, idempotent=True)
print(result.exit_code)                         # 0
print(json.loads(result.to_json())["data"])     # {'rows': 42}
```

Constructor fields include `success`, `data`, `error`, `error_code`, `context`,
`side_effects`, the three `hints_on_*` lists, `idempotent` and `version`.
Dictionary/list defaults use independent factories. `to_dict()` omits `None`
values, but retains empty collections and `False`; the JSON envelope therefore
contains more than just `success` and `data`.

```python
from scitex_dev import Result, RESULT_SCHEMA

result = Result(success=True, data=42)
print(result.to_dict()["data"])                # 42
print("success" in Result.json_schema()["properties"])  # True
print("data" in RESULT_SCHEMA["properties"])             # True
```

## Failures and error codes

```python
from scitex_dev import ErrorCode, Result

result = Result(
    success=False,
    error="Config file not found",
    error_code=ErrorCode.FILE_NOT_FOUND.value,
    hints_on_error=["Check the selected configuration path."],
)
print(result.exit_code)                        # 1
```

| Enum member | Code | Exit code |
|---|---|---|
| `OK` | `E000` | 0 |
| `VALIDATION` | `E001` | 2 |
| `FILE_NOT_FOUND` | `E002` | 1 |
| `PERMISSION` | `E003` | 4 |
| `DEPENDENCY` | `E004` | 3 |
| `TIMEOUT` | `E005` | 5 |
| `RATE_LIMITED` | `E006` | 5 |
| `NETWORK` | `E007` | 1 |
| `CONFIG` | `E008` | 2 |
| `CONFLICT` | `E009` | 6 |
| `INTERNAL` | `E999` | 1 |

`classify_exception` honors an exception's recognized `error_code` attribute
before its built-in exception mapping:

```python
from scitex_dev import ErrorCode, classify_exception

print(classify_exception(FileNotFoundError("x")) == ErrorCode.FILE_NOT_FOUND)  # True
print(classify_exception(ValueError("bad")) == ErrorCode.VALIDATION)          # True
print(classify_exception(ImportError("missing")) == ErrorCode.DEPENDENCY)     # True
```

## Opt-in wrapping

`@supports_return_as` preserves ordinary calls. Passing `return_as="result"`
requests an envelope, including conversion of exceptions into failed results:

```python
from scitex_dev import supports_return_as

@supports_return_as
def add(a: int, b: int) -> int:
    return a + b

print(add(1, 2))                              # 3
result = add(1, 2, return_as="result")
print(result.success, result.data)            # True 3

@supports_return_as
def divide(a: int, b: int) -> float:
    return a / b

failure = divide(1, 0, return_as="result")
print(failure.success, failure.error_code)     # False E999
```

## Side-effect metadata

`SideEffect` is a frozen declaration; constructing one does not perform the
operation. Current types are `file_create`, `file_modify`, `file_delete`,
`network`, `state_change` and `cache_write`.

```python
from scitex_dev import SideEffect

effect = SideEffect(type="file_create", target="results.csv", undoable=False)
print(str(effect))                           # file_create: results.csv
```

Pass declarations to an adapter such as
`wrap_as_mcp(handler, side_effects=[str(effect)], ...)` only when they describe
that handler's actual behavior. See [CLI/MCP adapters](11_cli-mcp-utils.md).
