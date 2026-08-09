---
description: |
  [TOPIC] Test quality — the TQ replacement patterns
  [DETAILS] The concrete before/after rewrites for each TQ smell: multi-assert → split into one-assertion tests (TQ007), multi-Act → one Act per test named for what each verifies, parametrize-body conditional → two parametrized tests with one intent each (TQ006), and session-scope-with-mutation → an immutable session template plus a per-test copy fixture (TQ004). Companion to [13_test-quality.md](13_test-quality.md).
tags: [scitex-general-package-test-quality]
---

# Test quality — replacement patterns

> Parent leaf: [`13_test-quality.md`](13_test-quality.md) — the TQ family rules, the TQ002 marker format, and the canonical shape live there; this leaf carries the before/after rewrites.

## Replacement patterns

### Multi-assert → split

```python
# BAD (TQ007)
def test_register_user():
    # Arrange / Act
    user = service.register(user_data)
    # Assert
    assert user.name == "Alice"
    assert user.is_active is True

# GOOD
def test_register_returns_user_with_supplied_name(): ...
def test_register_marks_returned_user_active(): ...
```

### Multi-Act → split

```python
# BAD (TQ007; the article calls this "Act が複数" — more than one Act)
def test_user_workflow():
    user = service.register(...)
    assert user.is_active is True
    service.deactivate(user.id)
    assert user.is_active is False

# GOOD: one Act per test, named for what each verifies.
def test_register_creates_active_user(): ...
def test_deactivate_sets_is_active_false(): ...
```

### Parametrize-body conditional → split

```python
# BAD (TQ006)
@pytest.mark.parametrize("v, e, raises", [
    ("a@b.c", True, False), (None, None, True),
])
def test_validate_email(v, e, raises):
    if raises:
        with pytest.raises(TypeError):
            validate_email(v)
    else:
        assert validate_email(v) == e

# GOOD: two parametrized tests, one intent each.
@pytest.mark.parametrize("v, e", [("a@b.c", True), ("x@y", False)])
def test_validate_email_returns_expected_for_valid_input(v, e): ...

@pytest.mark.parametrize("v", [None, 42, []])
def test_validate_email_raises_typeerror_for_non_string_input(v): ...
```

### Session-scope-with-mutation → function-scope or split

```python
# BAD (TQ004)
@pytest.fixture(scope="session")
def db():
    d = create_db()
    d.insert({"id": 1, "name": "Alice"})  # mutation!
    yield d
    d.drop()

# GOOD
@pytest.fixture(scope="session")
def db_template():
    """Immutable template — populate once per session."""
    d = create_db()
    d.insert({"id": 1, "name": "Alice"})
    yield d
    d.drop()

@pytest.fixture
def db(db_template):
    """Per-test copy — mutations are isolated."""
    return db_template.copy()
```
