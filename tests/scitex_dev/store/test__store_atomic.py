"""A rejected local mutation must not leave an operation for peers to replay."""

import psycopg

from scitex_dev.store import NEW_RECORD


def _table(store, kind):
    name = getattr(store.dialect, kind + "_table")(store.schema)
    return store.dialect.quote(name)


def _refuse_materialization(store):
    store._connection.execute(
        f"ALTER TABLE {_table(store, 'rows')} "
        "ADD CONSTRAINT owned_refuse_row_write CHECK (false) NOT VALID"
    )


def _op_count(store):
    return store._connection.execute(
        f"SELECT count(*) AS n FROM {_table(store, 'oplog')}"
    ).fetchone()["n"]


def _constraint_error(call):
    try:
        call()
    except psycopg.errors.CheckViolation as error:
        return error
    return None


def test_row_and_operation_commit_in_the_same_postgres_transaction(local):
    # Arrange
    # Capture the top-level transaction ID; xmin can name a SAVEPOINT subtransaction.
    local._connection.execute("CREATE TABLE owned_write_xids (xid bigint)")
    local._connection.execute(
        "CREATE FUNCTION owned_capture_write_xid() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN "
        "INSERT INTO owned_write_xids VALUES (txid_current()); "
        "RETURN NEW; END $$"
    )
    for kind in ("oplog", "rows"):
        local._connection.execute(
            f"CREATE TRIGGER owned_capture_write_xid AFTER INSERT ON {_table(local, kind)} "
            "FOR EACH ROW EXECUTE FUNCTION owned_capture_write_xid()"
        )
    # Act
    local.put({"id": "one", "status": "open"}, expected_revision=NEW_RECORD)
    observed = local._connection.execute("SELECT xid FROM owned_write_xids").fetchall()
    # Assert
    assert len(observed) == 2 and len({row["xid"] for row in observed}) == 1


def test_rejected_put_leaves_no_operation_for_replication(local):
    # Arrange
    _refuse_materialization(local)
    # Act
    error = _constraint_error(
        lambda: local.put(
            {"id": "rejected", "status": "open"}, expected_revision=NEW_RECORD
        )
    )
    # Assert
    assert (
        isinstance(error, psycopg.errors.CheckViolation),
        _op_count(local),
        local.rows(),
    ) == (True, 0, [])


def test_rejected_hide_does_not_publish_an_operation(local):
    # Arrange
    created = local.put({"id": "one", "status": "open"}, expected_revision=NEW_RECORD)
    _refuse_materialization(local)
    # Act
    error = _constraint_error(
        lambda: local.hide({"id": "one"}, expected_revision=created.revision)
    )
    # Assert
    assert (
        isinstance(error, psycopg.errors.CheckViolation),
        _op_count(local),
        local.get({"id": "one"}) is not None,
    ) == (True, 1, True)


def test_rejected_unhide_does_not_publish_an_operation(local):
    # Arrange
    created = local.put({"id": "one", "status": "open"}, expected_revision=NEW_RECORD)
    hidden = local.hide({"id": "one"}, expected_revision=created.revision)
    _refuse_materialization(local)
    # Act
    error = _constraint_error(
        lambda: local.unhide({"id": "one"}, expected_revision=hidden.revision)
    )
    # Assert
    assert (
        isinstance(error, psycopg.errors.CheckViolation),
        _op_count(local),
        local.get({"id": "one"}) is None,
    ) == (True, 2, True)
