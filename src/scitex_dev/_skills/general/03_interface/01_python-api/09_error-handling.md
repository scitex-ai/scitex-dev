---
description: |
  [TOPIC] Interface Python Api Error Handling
  [DETAILS] Standard Python exceptions and the public scitex_dev ErrorCode,
  ScitexError and classify_exception interfaces for structured failures.
tags: [scitex-general-interface-python-api-error-handling]
---

# Error handling

Use standard Python exceptions inside Python code. At a structured CLI, MCP or
HTTP boundary, use the public exports `ErrorCode`, `ScitexError` and
`classify_exception` from `scitex_dev`. The implementation is
`scitex_dev/_core/errors.py`; consumers do not import its private module path.

## Python failures

```python
from pathlib import Path


def require_new_path(path):
    target = Path(path)
    if target.exists():
        raise FileExistsError(f"{target} already exists")
    return target
```

Use `ValueError` for invalid values, `TypeError` for invalid types,
`FileNotFoundError` for missing files, and `PermissionError` for denied access.
Retain the original exception when translating a failure at a boundary.

## Structured failures

```python
from scitex_dev import ErrorCode, ScitexError

error = ScitexError(
    "h5py not installed",
    code=ErrorCode.DEPENDENCY,
    remediation="pip install scitex-io[h5]",
)
assert error.to_dict() == {
    "code": "E004",
    "message": "h5py not installed",
    "remediation": "pip install scitex-io[h5]",
}
```

`ScitexError(message, *, code=ErrorCode.INTERNAL, remediation=None)` stores the
category as `error.error_code`. Its dictionary contains `code` and `message`,
plus `remediation` when supplied. It does not include a traceback. CLI and MCP
adapters can wrap this dictionary in their own result envelope; verify the
adapter's actual response rather than assuming the dictionary is its entire
wire response. Keep secrets and internal server details out of public messages.

| Enum member | Value | CLI exit code |
| --- | --- | --- |
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

These are the implemented names. Names such as `E004_DEPENDENCY_MISSING` and
an allocated per-package code range are not part of this registry. Do not
subclass a populated Python enum to add members. Map a domain failure to an
existing category; propose additional shared categories through the owning
source and tests when needed.

## Classifying and chaining exceptions

```python
from scitex_dev import ErrorCode, ScitexError, classify_exception

assert classify_exception(FileNotFoundError("missing")) == ErrorCode.FILE_NOT_FOUND
assert classify_exception(ValueError("invalid")) == ErrorCode.VALIDATION

try:
    raise ImportError("optional dependency unavailable")
except ImportError as cause:
    error = ScitexError("Optional dependency unavailable", code=ErrorCode.DEPENDENCY)
    assert classify_exception(error) == ErrorCode.DEPENDENCY
    # A boundary that raises the translated error uses: raise error from cause
```

`classify_exception` checks an exception's `error_code`, then its built-in
exception category, and otherwise returns `INTERNAL`. An error's
`ErrorCode.exit_code` supplies the CLI mapping.

Evidence: `tests/scitex_dev/_core/test_errors.py` exercises the category values,
classification, exception attributes and dictionary serialization. Audit rules
and future code allocations must be described separately from these implemented
runtime interfaces.
