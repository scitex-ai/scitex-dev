# SciTeX Package Architecture

## 3-Layer Cascade

```
Downstream (standalone apps — own IO, own GUI, unit tests):
  figrecipe, scitex-writer, scitex-scholar, scitex-clew, ...

Middle (shared infrastructure — integration tests):
  scitex-io, scitex-app, scitex-ui, scitex-stats, scitex-audio, scitex-dev

Upstream (SOC orchestration — integration tests ONLY):
  scitex (~/proj/scitex-python), scitex-cloud
```

## Rules
- Apps work standalone — no scitex for core functionality
- Middle wraps downstream via plugin registry (never replaces)
- Upstream re-exposes only — no own logic, SOC
- Never reverse imports — upstream never imports downstream directly
- `_AVAILABLE` flags + extras for optional dependencies
