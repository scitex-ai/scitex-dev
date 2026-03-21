# SciTeX Upstream and Downstream Rules

## Package Dependency Direction

```
Downstream (apps — standalone, own IO, own GUI)
    figrecipe, scitex-writer, scitex-scholar, scitex-clew, ...
        ↑ wraps/cascades via plugin registry
Middle layer (shared infrastructure)
    scitex-io    — universal IO (wraps downstream IO with type checking)
    scitex-app   — shared backends (FilesBackend, ChatBackend)
    scitex-ui    — shared React components (Workspace, Viewer, DataTable)
    scitex-stats — statistical tests
    scitex-audio — TTS/audio
        ↑ integrates/re-exposes
Upstream (orchestration — SOC, integration tests only)
    scitex       — full ecosystem (session, IO, stats, plt, scholar)
    scitex-cloud — deployment (SLURM, auth, multi-user)
```

## Core Principles

### 1. Downstream Apps Must Work Standalone
- **figrecipe** must function without scitex installed
- `fr.save()`, `fr.load()`, `fr.reproduce()` work independently
- GUI (`figrecipe gui`) works without scitex
- All core tests pass without scitex
- Same applies to Writer, Scholar, Clew, etc.

### 2. Middle Layer Wraps, Not Replaces
- scitex-io provides universal `stx.io.save()` / `stx.io.load()`
- It **wraps** downstream IO (cascades through plugin registry)
- It adds type checking, format detection, and standardization
- Downstream apps register their formats via entry points
- scitex-ui provides shared React components, not app-specific logic
- scitex-app provides shared Python backends

### 3. Upstream Orchestrates (SOC)
- **scitex** is an orchestration package — Separation of Concerns
- `@stx.session` provides reproducible experiment tracking
- Session wraps figrecipe output with organized directories
- Session uses scitex-io for file operations
- Session is **optional** — downstream apps work without it
- **scitex has NO logic of its own** — only re-exposes and integrates

### 4. Upstream Has ONLY Integration Tests
- **Downstream (figrecipe)**: unit tests — test own logic
- **Middle (scitex-io)**: integration tests — does cascade work?
- **Upstream (scitex)**: integration tests ONLY — does the full pipeline flow?
- Each layer tests **its own responsibility**, never downstream logic
- This ensures bugs are caught at the correct scope

### 5. Examples Are the Exception
- Examples CAN use `@stx.session` for organized output (logs, directories)
- This is for user convenience — linked outputs in one place
- Gallery CI installs scitex for examples but must handle failure gracefully
- If scitex install fails, examples should fallback or skip gracefully

## Testing Scope

```
Layer           Test Scope                          Example
-----------     --------------------------------    ---------------------------
figrecipe       Unit: fr.save() works?              test_save_produces_yaml_png
                Unit: fr.reproduce() works?         test_reproduce_matches
                Unit: GUI renders?                  test_editor_elements

scitex-io       Integration: cascade works?         test_stx_io_save_calls_fr_save
                Integration: type checking?         test_invalid_type_raises
                Integration: plugin discovery?      test_figrecipe_plugin_found

scitex          Integration: full pipeline?         test_session_saves_via_io
                Integration: all apps accessible?   test_import_all_subpackages
                NO unit tests for downstream logic
```

## Special IO Pattern (Cascade Direction)

### Downstream packages define their own IO
```python
# figrecipe defines its own save/load for .yaml + .png
def save(fig, path, **kwargs):
    """Save figure as recipe YAML + PNG."""
    ...  # figrecipe-specific logic

def load(path):
    """Load recipe from YAML."""
    ...

# Register with scitex-io plugin registry (if available)
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
def save(obj, path, **kwargs):
    """Universal save — detects format, delegates to downstream plugin."""
    ext = Path(path).suffix
    plugin = _registry.get(ext)
    if plugin:
        return plugin.save(obj, path, **kwargs)  # Cascade to downstream
    # Fallback: standard formats (CSV, NPY, PKL, etc.)
    ...
```

### scitex re-exposes without modification
```python
# scitex just re-exports — NO additional logic
from scitex_io import save, load  # Re-expose as stx.io.save()
```

### The cascade flows through ALL 3 interfaces

```
                    Python API          CLI Command           MCP Server
                    ----------          -----------           ----------
figrecipe           fr.save()           figrecipe save        plt_plot (MCP)
                        ↑                    ↑                    ↑
scitex-io           stx.io.save()       scitex io save        io_save (MCP)
                        ↑                    ↑                    ↑
scitex              stx.io.save()       scitex io save        io_save (MCP)
                    (re-exposed)        (re-exposed)          (re-exposed)
```

### Cascade rules
1. **Downstream defines** — each app implements save/load for its formats
2. **scitex-io detects** — discovers downstream plugins via entry points or registry
3. **scitex re-exposes** — no additional wrapping, just re-export
4. **Type checking** — scitex-io validates input/output types during cascade
5. **All 3 interfaces** — Python API, CLI, and MCP server cascade same direction
6. **Never reverse** — upstream never imports from downstream directly

## Optional Dependency Pattern

### Use extras in pyproject.toml
```toml
[project.optional-dependencies]
scitex = ["scitex[io,session]>=2.24.0"]
all = ["figrecipe[scitex]", "figrecipe[dev]"]
```

### Use _AVAILABLE flags in code
```python
try:
    import scitex as stx
    _SCITEX_AVAILABLE = True
except ImportError:
    _SCITEX_AVAILABLE = False
```

### Provide clear instructions on missing deps
```python
def some_feature_requiring_scitex():
    if not _SCITEX_AVAILABLE:
        raise ImportError(
            "This feature requires scitex. "
            "Install it with: pip install figrecipe[scitex]"
        )
```

### Examples: graceful fallback
```python
try:
    import scitex as stx
    @stx.session
    def main(CONFIG=stx.INJECTED, plt=stx.INJECTED, ...):
        ...
except ImportError:
    def main():
        import figrecipe as fr
        fig, ax = fr.subplots()
        ...
```

## Shared UI Rules (scitex-ui)

### scitex-ui Is Infrastructure
- Provides reusable React components (Workspace, Viewer, DataTable, etc.)
- Ported from scitex-cloud (the reference implementation)
- All apps consume scitex-ui — apps only provide app-specific content
- Port from scitex-cloud, never create new implementations

### scitex-app Is Backend Infrastructure
- Provides shared backends (FilesBackend, ChatBackend, etc.)
- Apps consume scitex-app for file operations, chat, etc.
- Zero runtime dependencies — pure Python SDK

### Apps Only Contain App-Specific Code
- figrecipe: Canvas, PlotTypeNav, Properties, Gallery
- Writer: Editor, Bibliography, Claims
- Scholar: Search, Library, Citations

## CI Rules

### Downstream CI (figrecipe Tests)
- Install: `pip install -e ".[dev]"` — standalone only
- Must NOT require scitex
- Tests downstream logic only

### Downstream CI (figrecipe Gallery)
- Install: `pip install -e ".[all]"` + optional `pip install scitex`
- If scitex fails: warn, skip session examples, run plain ones

### Middle CI (scitex-io)
- Install: `pip install -e ".[dev]"` + downstream packages
- Integration tests: does cascade work through plugin registry?

### Upstream CI (scitex)
- Full integration: all packages installed
- Integration tests ONLY — does the full pipeline flow?
- NO unit tests for downstream functionality

## Version Compatibility

- Downstream specifies: `scitex-io >= X.Y` as optional dependency
- Middle specifies: downstream packages as optional test dependencies
- Upstream specifies: all packages with version ranges
- Breaking changes: coordinate across packages with version bumps
