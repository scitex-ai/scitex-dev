# SciTeX Shared UI (scitex-ui)

## Rule: Port from scitex-cloud, never create new implementations

- scitex-cloud is the reference implementation
- scitex-ui generalizes scitex-cloud components as reusable React/TS
- Apps consume scitex-ui — only provide app-specific content

## Shared components (all from scitex-cloud)
- Workspace shell (Console/Chat | Files | Viewer | App Content)
- Terminal, Chat, FileBrowser, Viewer, DataTable
- Context menu, Ctrl+K search, drag-drop, resizers

## Apps only contain
- figrecipe: Canvas, PlotTypeNav, Properties, Gallery
- Writer: Editor, Bibliography, Claims
- Scholar: Search, Library, Citations
