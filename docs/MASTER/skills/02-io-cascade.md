# SciTeX IO Cascade Pattern

## Direction: downstream → scitex-io → scitex

1. **Downstream defines** — figrecipe implements `save()`/`load()` for its formats
2. **scitex-io detects** — discovers plugins via entry points, delegates with type checking
3. **scitex re-exposes** — just re-exports from scitex-io, no additional logic

## All 3 Interfaces Cascade

```
                Python API          CLI Command           MCP Server
figrecipe       fr.save()           figrecipe save        plt_plot
                    ↑                    ↑                    ↑
scitex-io       stx.io.save()       scitex io save        io_save
                    ↑                    ↑                    ↑
scitex          stx.io.save()       scitex io save        io_save
                (re-exposed)        (re-exposed)          (re-exposed)
```
