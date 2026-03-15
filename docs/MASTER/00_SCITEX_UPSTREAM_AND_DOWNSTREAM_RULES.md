# SciTeX Upstream and Downstream Rules

## Package Dependency Direction

```
figrecipe (standalone app — own IO, own GUI)
    ↑ wraps/cascades
scitex-io (universal IO interface — wraps figrecipe's IO with type checking)
    ↑ integrates
scitex (full ecosystem — session, IO, stats, plt, scholar)
```

## Core Rules

### 1. Apps Must Work Standalone
- **figrecipe** must function without scitex installed
- `fr.save()`, `fr.load()`, `fr.reproduce()` work independently
- GUI (`figrecipe gui`) works without scitex
- All core tests pass without scitex

### 2. scitex-io Wraps, Not Replaces
- scitex-io provides universal `stx.io.save()` / `stx.io.load()`
- It **wraps** figrecipe's native save/load (cascades through)
- It adds type checking, format detection, and standardization
- figrecipe registers its formats with scitex-io's plugin registry

### 3. scitex Integrates
- `@stx.session` provides reproducible experiment tracking
- Session wraps figrecipe's output with organized directories
- Session uses scitex-io for file operations
- Session is **optional** — apps work without it

### 4. Integration Tests Belong Upstream
- **figrecipe** tests: standalone functionality only
- **scitex-io** tests: IO wrapping, format cascading, type checking
- **scitex** tests: full integration (session + IO + apps)
- Each upstream package is responsible for testing its own integration

### 5. Examples Are the Exception
- Examples CAN use `@stx.session` for organized output (logs, directories)
- This is for user convenience — linked outputs in one place
- Gallery CI installs scitex for examples but must handle failure gracefully
- If scitex install fails, Gallery should skip session-dependent examples

## CI Rules

### figrecipe CI (Tests workflow)
- Install: `pip install -e ".[dev]"` — standalone only
- Must NOT require scitex
- Tests figrecipe core functionality

### figrecipe CI (Gallery workflow)
- Install: `pip install -e ".[all]"` + optional `pip install scitex[io,session]`
- If scitex install fails: skip session-decorated examples, run plain ones
- Gallery output demonstrates figrecipe capabilities

### scitex-io CI
- Install: `pip install -e ".[dev]"` + figrecipe, scitex-stats, etc.
- Tests IO wrapping and format cascading
- Integration tests: can figrecipe's save/load work through scitex-io?

### scitex CI
- Full integration: all packages installed
- Tests session decorator with real apps
- Tests end-to-end workflows

## Shared UI Rules (scitex-ui)

### scitex-ui Is Infrastructure
- Provides reusable React components (Workspace, Viewer, DataTable, etc.)
- Ported from scitex-cloud (the reference implementation)
- All apps consume scitex-ui — apps only provide app-specific content

### scitex-app Is Backend Infrastructure
- Provides shared backends (FilesBackend, ChatBackend, etc.)
- Apps consume scitex-app for file operations, chat, etc.
- Zero runtime dependencies — pure Python SDK

### Apps Only Contain App-Specific Code
- figrecipe: Canvas, PlotTypeNav, Properties, Gallery (app-specific)
- Writer: Editor, Bibliography, Claims (app-specific)
- Scholar: Search, Library, Citations (app-specific)

## Optional Dependency Pattern

### Use extras in pyproject.toml
```toml
[project.optional-dependencies]
scitex = ["scitex[io,session]>=2.24.0"]
all = ["figrecipe[scitex]", "figrecipe[dev]"]
```

### Use _AVAILABLE flags in code
```python
# At module level — detect optional dependencies
try:
    import scitex as stx
    _SCITEX_AVAILABLE = True
except ImportError:
    _SCITEX_AVAILABLE = False

try:
    from scitex_app.chat import stream_chat
    _SCITEX_APP_AVAILABLE = True
except ImportError:
    _SCITEX_APP_AVAILABLE = False
```

### Provide clear instructions on missing deps
```python
def some_feature_requiring_scitex():
    if not _SCITEX_AVAILABLE:
        raise ImportError(
            "This feature requires scitex. "
            "Install it with: pip install figrecipe[scitex]"
        )
    # ... feature code
```

### Examples: graceful fallback
```python
try:
    import scitex as stx
    @stx.session
    def main(CONFIG=stx.INJECTED, plt=stx.INJECTED, ...):
        ...
except ImportError:
    # Fallback: run without session management
    def main():
        import figrecipe as fr
        fig, ax = fr.subplots()
        ...
```

## Special IO Pattern (Cascade Direction)

### Downstream packages define their own IO
```python
# figrecipe defines its own save/load for .yaml + .png
# In figrecipe/io.py:
def save(fig, path, **kwargs):
    """Save figure as recipe YAML + PNG."""
    # figrecipe-specific logic
    ...

def load(path):
    """Load recipe from YAML."""
    ...

# Register with scitex-io's plugin registry (if available)
FIGRECIPE_IO_SPEC = {
    "extensions": [".yaml", ".yml"],
    "save": save,
    "load": load,
    "description": "FigRecipe YAML recipe format",
}
```

### scitex-io detects and handles as downstream intended
```python
# scitex-io auto-discovers downstream IO plugins
# In scitex_io/__init__.py:
def save(obj, path, **kwargs):
    """Universal save — detects format, delegates to downstream plugin."""
    ext = Path(path).suffix
    plugin = _registry.get(ext)
    if plugin:
        return plugin.save(obj, path, **kwargs)  # Cascade to downstream
    # Fallback: standard formats (CSV, NPY, PKL, etc.)
    ...
```

### scitex-python re-exposes without modification
```python
# scitex/__init__.py or scitex/io/__init__.py:
# Just re-export from scitex-io — no additional logic
from scitex_io import save, load  # Re-expose as stx.io.save()
```

### The cascade flows through 3 interfaces

```
                    Python API          CLI Command           MCP Server
                    ----------          -----------           ----------
figrecipe           fr.save()           figrecipe save        plt_plot (MCP)
                        ↑                    ↑                    ↑
scitex-io           stx.io.save()       scitex io save        io_save (MCP)
                        ↑                    ↑                    ↑
scitex               stx.io.save()      scitex io save        io_save (MCP)
                    (re-exposed)        (re-exposed)          (re-exposed)
```

### Rules for cascade
1. **Downstream defines** — figrecipe implements `save()` and `load()` for its formats
2. **scitex-io detects** — discovers downstream plugins via entry points or registry
3. **scitex re-exposes** — no additional wrapping, just re-export
4. **Type checking** — scitex-io validates input/output types during cascade
5. **All 3 interfaces** — Python API, CLI, and MCP server must cascade in the same direction
6. **Never reverse** — scitex should never import from figrecipe directly; only through scitex-io's plugin system

## Version Compatibility

- figrecipe specifies: `scitex-io >= X.Y` as optional dependency
- scitex-io specifies: `figrecipe` as optional test dependency
- scitex specifies: all packages with version ranges
- Breaking changes: coordinate across packages with version bumps
