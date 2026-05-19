"""Assert the initial Alembic migration produces the schema in tech-spec §3."""

from __future__ import annotations

import sqlalchemy as sa


def test_all_tables_exist() -> None:
    from uniqlo_sales_alerter.db.engine import engine

    sync_engine = sa.create_engine(engine.url.render_as_string(hide_password=False).replace(
        "sqlite+aiosqlite:///", "sqlite:///"
    ))
    inspector = sa.inspect(sync_engine)
    tables = set(inspector.get_table_names())
    expected = {
        "saved_filters",
        "watched_variants",
        "ignored_products",
        "ignored_keywords",
        "seen_variants",
        "check_history",
        "deal_observations",
        "notification_log",
        "migrations_applied",
        "_health_probe",
        "alembic_version",
    }
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


def test_saved_filters_check_constraint_rejects_bad_availability_mode() -> None:
    """The CHECK constraint must reject availability_mode values outside the allowed set."""
    from uniqlo_sales_alerter.db.engine import engine

    sync_url = engine.url.render_as_string(hide_password=False).replace(
        "sqlite+aiosqlite:///", "sqlite:///"
    )
    sync_engine = sa.create_engine(sync_url)
    with sync_engine.begin() as conn:
        try:
            conn.execute(
                sa.text(
                    "INSERT INTO saved_filters "
                    "(name, gender, min_discount, sizes_clothing, sizes_pants, sizes_shoes,"
                    " one_size_match, availability_mode, ignored_keywords, enabled)"
                    " VALUES ('bad-mode', '[]', 0, '[]', '[]', '[]', 0, 'invalid', '[]', 1)"
                )
            )
            raised = False
        except sa.exc.IntegrityError:
            raised = True
        # Clean up the row in case the constraint did not fire (would be a bug).
        conn.execute(sa.text("DELETE FROM saved_filters WHERE name='bad-mode'"))
    assert raised, "expected CHECK constraint to reject 'invalid' availability_mode"


def test_ignored_keywords_collate_nocase() -> None:
    """Duplicate keyword in different cases should fail the unique constraint."""
    from uniqlo_sales_alerter.db.engine import engine

    sync_url = engine.url.render_as_string(hide_password=False).replace(
        "sqlite+aiosqlite:///", "sqlite:///"
    )
    sync_engine = sa.create_engine(sync_url)
    with sync_engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO ignored_keywords (keyword) VALUES ('Promo')"))
        try:
            conn.execute(sa.text("INSERT INTO ignored_keywords (keyword) VALUES ('promo')"))
            duplicate_inserted = True
        except sa.exc.IntegrityError:
            duplicate_inserted = False
        conn.execute(sa.text("DELETE FROM ignored_keywords WHERE keyword='Promo'"))
    assert not duplicate_inserted, "NOCASE collation should have rejected 'promo' duplicate"


def test_named_indexes_present() -> None:
    """All indexes named in tech spec §3 must exist."""
    from uniqlo_sales_alerter.db.engine import engine

    sync_url = engine.url.render_as_string(hide_password=False).replace(
        "sqlite+aiosqlite:///", "sqlite:///"
    )
    sync_engine = sa.create_engine(sync_url)
    inspector = sa.inspect(sync_engine)
    index_names: set[str] = set()
    for table in ("seen_variants", "check_history", "deal_observations", "notification_log"):
        for idx in inspector.get_indexes(table):
            index_names.add(idx["name"])
    expected = {
        "idx_seen_variants_product",
        "idx_check_history_ran_at",
        "idx_deal_observations_observed_at",
        "idx_deal_observations_is_deep",
        "idx_notification_log_sent_at",
    }
    assert expected.issubset(index_names), f"missing indexes: {expected - index_names}"
