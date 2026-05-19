"""initial schema

Creates the full schema described in docs/specs/03-tech-spec.md section 3:
ten tables plus the named indexes and CHECK constraint. JSON-array columns
are stored as TEXT at the DDL layer (the ``JSONList`` TypeDecorator only
affects ORM round-tripping). The ``ignored_keywords.keyword`` column gets
the ``NOCASE`` collation so substring matching is case-insensitive.

Revision ID: 22d23a5639f1
Revises:
Create Date: 2026-05-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "22d23a5639f1"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "_health_probe",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "probed_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "check_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "ran_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("deals_scanned", sa.Integer(), nullable=False),
        sa.Column("deals_matched", sa.Integer(), nullable=False),
        sa.Column("deep_discounts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("check_history", schema=None) as batch_op:
        batch_op.create_index("idx_check_history_ran_at", ["ran_at"], unique=False)

    op.create_table(
        "deal_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("discount_pct", sa.Float(), nullable=True),
        sa.Column("is_deep", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("deal_observations", schema=None) as batch_op:
        batch_op.create_index("idx_deal_observations_is_deep", ["is_deep"], unique=False)
        batch_op.create_index(
            "idx_deal_observations_observed_at", ["observed_at"], unique=False
        )

    op.create_table(
        "ignored_keywords",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.Text(collation="NOCASE"), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("keyword"),
    )

    op.create_table(
        "ignored_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )

    op.create_table(
        "migrations_applied",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name"),
    )

    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("filter_ids", sa.Text(), nullable=False),
        sa.Column("deal_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("notification_log", schema=None) as batch_op:
        batch_op.create_index("idx_notification_log_sent_at", ["sent_at"], unique=False)

    op.create_table(
        "saved_filters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("gender", sa.Text(), nullable=False),
        sa.Column("min_discount", sa.Float(), nullable=False),
        sa.Column("sizes_clothing", sa.Text(), nullable=False),
        sa.Column("sizes_pants", sa.Text(), nullable=False),
        sa.Column("sizes_shoes", sa.Text(), nullable=False),
        sa.Column("one_size_match", sa.Integer(), nullable=False),
        sa.Column("availability_mode", sa.Text(), nullable=False),
        sa.Column("ignored_keywords", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("snooze_until", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "availability_mode IN ('online', 'in_store', 'both')",
            name="ck_saved_filters_availability_mode",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "seen_variants",
        sa.Column("variant_key", sa.Text(), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("color_code", sa.Text(), nullable=False),
        sa.Column("size_code", sa.Text(), nullable=False),
        sa.Column("discount_pct", sa.Float(), nullable=True),
        sa.Column(
            "last_seen_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("variant_key"),
    )
    with op.batch_alter_table("seen_variants", schema=None) as batch_op:
        batch_op.create_index("idx_seen_variants_product", ["product_id"], unique=False)

    op.create_table(
        "watched_variants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("color_code", sa.Text(), nullable=False),
        sa.Column("size_code", sa.Text(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("watched_variants", schema=None) as batch_op:
        batch_op.create_index(
            "uq_watched_variants_pid_color_size",
            ["product_id", "color_code", "size_code"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("watched_variants", schema=None) as batch_op:
        batch_op.drop_index("uq_watched_variants_pid_color_size")
    op.drop_table("watched_variants")

    with op.batch_alter_table("seen_variants", schema=None) as batch_op:
        batch_op.drop_index("idx_seen_variants_product")
    op.drop_table("seen_variants")

    op.drop_table("saved_filters")

    with op.batch_alter_table("notification_log", schema=None) as batch_op:
        batch_op.drop_index("idx_notification_log_sent_at")
    op.drop_table("notification_log")

    op.drop_table("migrations_applied")
    op.drop_table("ignored_products")
    op.drop_table("ignored_keywords")

    with op.batch_alter_table("deal_observations", schema=None) as batch_op:
        batch_op.drop_index("idx_deal_observations_observed_at")
        batch_op.drop_index("idx_deal_observations_is_deep")
    op.drop_table("deal_observations")

    with op.batch_alter_table("check_history", schema=None) as batch_op:
        batch_op.drop_index("idx_check_history_ran_at")
    op.drop_table("check_history")

    op.drop_table("_health_probe")
