---
description: |
  [TOPIC] CLI and MCP adapters
  [DETAILS] Format Result envelopes, adapt plain or decorated functions to CLI/MCP output and add shared Click or argparse flags. Distinguish process-exiting CLI calls from MCP JSON-returning helpers.
tags: [scitex-dev-cli-mcp-utils]
---

# CLI and MCP adapters

## Format an existing Result

`handle_result(result, as_json=False, file=None)` prints the chosen representation
and returns an exit code; it does not exit the process:

```python
from io import StringIO
from scitex_dev import Result, handle_result

output = StringIO()
code = handle_result(Result(success=True, data={"count": 5}), as_json=True, file=output)
print(code)                                  # 0
print('"count": 5' in output.getvalue())       # True
```

JSON mode serializes the full envelope. Human mode prints successful data or an
error and recovery hints. Inspect the owning `_cli/_utils.py` implementation for
stream selection and formatting details.

## CLI execution

`run_as_cli` calls a `@supports_return_as` function; `wrap_as_cli` adapts a plain
function. Both accept `as_json` and function keyword arguments, format a Result
and exit with its code. Run these examples as CLI entry points:

```python
from scitex_dev import run_as_cli, supports_return_as

@supports_return_as
def doubled(n: int) -> int:
    return n * 2

run_as_cli(doubled, as_json=True, n=5)          # Prints Result JSON; exits 0.
```

```python
from scitex_dev import wrap_as_cli

def count_rows(n: int) -> dict:
    return {"count": n * 2}

wrap_as_cli(count_rows, as_json=True, n=5)      # Prints Result JSON; exits 0.
```

## MCP execution

`run_as_mcp` calls a decorated function and returns JSON. `wrap_as_mcp` wraps a
plain function without requiring a decorator:

```python
import json
from scitex_dev import run_as_mcp, supports_return_as, wrap_as_mcp

@supports_return_as
def doubled(n: int) -> int:
    return n * 2

print(json.loads(run_as_mcp(doubled, n=5))["data"])  # 10

payload = wrap_as_mcp(lambda n: {"count": n * 2}, n=5, idempotent=True)
print(json.loads(payload)["data"])                 # {'count': 10}
```

`wrap_as_mcp` and `async_wrap_as_mcp` accept `side_effects`, `hints_on_error` and
`idempotent` adapter metadata separately from function keyword arguments.
Declare actual behavior; metadata does not enforce permissions or undo changes.

```python
import asyncio
import json
from scitex_dev import async_wrap_as_mcp

async def doubled(n: int) -> int:
    return n * 2

async def main() -> None:
    payload = await async_wrap_as_mcp(doubled, n=5, idempotent=True)
    print(json.loads(payload)["data"])             # 10

asyncio.run(main())
```

Use `result_to_mcp` when the Result already exists:

```python
import json
from scitex_dev import Result, result_to_mcp

payload = result_to_mcp(Result(success=True, data=42))
print(json.loads(payload)["data"])                 # 42
```

## Shared flags

| Helper | Effect |
|---|---|
| `@json_option` | Adds Click `--json`, passed as `as_json` |
| `@dry_run_option` | Adds Click `--dry-run` |
| `add_json_argument(parser)` | Adds argparse JSON output selection |
| `add_dry_run_argument(parser)` | Adds argparse preview selection |

The decorators import Click lazily; Click is a declared dependency in the current
Dev distribution. Flags still need real implementation in the command callback.

```python
import click
from scitex_dev import dry_run_option, json_option

@click.command()
@json_option
@dry_run_option
def command(as_json: bool, dry_run: bool) -> None:
    click.echo({"as_json": as_json, "dry_run": dry_run})
```

## Register a leaf tool

With FastMCP installed, define a local server and register the owning handler:

```python
from fastmcp import FastMCP
from scitex_dev import wrap_as_mcp

mcp = FastMCP("owned-example")

@mcp.tool()
def doubled(n: int) -> str:
    return wrap_as_mcp(lambda n: n * 2, n=n, idempotent=True)
```

Registration alone does not prove client visibility or execution. Verify the
actual connected server's list and call operations separately. The adapters
live in `_cli/_utils.py` and `_ecosystem/_mcp/_utils.py`; leaf handlers retain
ownership of domain logic.
