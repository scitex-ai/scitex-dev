# SciTeX Testing Scope

## Each layer tests its own responsibility

| Layer | Test Type | Example |
|-------|-----------|---------|
| Downstream (figrecipe) | **Unit tests** | `test_save_produces_yaml_png` |
| Middle (scitex-io) | **Integration tests** | `test_stx_io_save_calls_fr_save` |
| Upstream (scitex) | **Integration tests ONLY** | `test_session_saves_via_io` |

## Key principle
- Upstream (scitex) is SOC — Separation of Concerns orchestration
- Upstream has NO logic of its own → NO unit tests needed
- Bugs should be caught at the correct scope (downstream)
- This prevents duplicate tests across packages
