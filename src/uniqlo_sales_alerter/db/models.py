"""SQLAlchemy declarative models matching docs/specs/03-tech-spec.md section 3.

Tables created here back the new saved-filter, snooze, watched-variant,
ignored-product/keyword, seen-variant, check-history, deal-observation, and
notification-log features. The matcher and notification dispatcher still run
against legacy state (``config.yaml`` filters + ``.seen_variants.json``) for
the foundation phase; these tables stay empty until step 8 wires them in.

JSON-array columns are stored as TEXT with a ``JSONList`` :class:`TypeDecorator`
that round-trips through ``json.loads``/``json.dumps``. SQLite has no native
array type and the spec deliberately keeps the schema portable.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    Text,
    TypeDecorator,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class JSONList(TypeDecorator[list[Any]]):
    """Store a Python list as a JSON-encoded TEXT column."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: list[Any] | None, dialect: Any) -> str:
        if value is None:
            return "[]"
        return json.dumps(value)

    def process_result_value(self, value: str | None, dialect: Any) -> list[Any]:
        if value is None or value == "":
            return []
        return json.loads(value)


class SavedFilter(Base):
    """Named, independent filter set — the headline feature of the fork."""

    __tablename__ = "saved_filters"
    __table_args__ = (
        CheckConstraint(
            "availability_mode IN ('online', 'in_store', 'both')",
            name="ck_saved_filters_availability_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    gender: Mapped[list[str]] = mapped_column(JSONList, nullable=False, default=list)
    min_discount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sizes_clothing: Mapped[list[str]] = mapped_column(JSONList, nullable=False, default=list)
    sizes_pants: Mapped[list[str]] = mapped_column(JSONList, nullable=False, default=list)
    sizes_shoes: Mapped[list[str]] = mapped_column(JSONList, nullable=False, default=list)
    one_size_match: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    availability_mode: Mapped[str] = mapped_column(Text, nullable=False, default="both")
    ignored_keywords: Mapped[list[str]] = mapped_column(JSONList, nullable=False, default=list)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class WatchedVariant(Base):
    """A specific product/colour/size combination tracked regardless of sale status."""

    __tablename__ = "watched_variants"
    __table_args__ = (
        Index(
            "uq_watched_variants_pid_color_size",
            "product_id",
            "color_code",
            "size_code",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(Text, nullable=False)
    color_code: Mapped[str] = mapped_column(Text, nullable=False)
    size_code: Mapped[str] = mapped_column(Text, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class IgnoredProduct(Base):
    """Permanent product-level ignore by product ID."""

    __tablename__ = "ignored_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class IgnoredKeyword(Base):
    """Global ignored keyword. Per-filter ignored keywords live on ``SavedFilter``."""

    __tablename__ = "ignored_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # COLLATE NOCASE is added by hand in the initial migration; SQLAlchemy
    # exposes ``sqlite_collate`` but it is dialect-specific and we want the
    # explicit DDL to live in the migration script for portability.
    keyword: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class SeenVariant(Base):
    """Variant-key set used by the matcher to classify deals as new vs. already-seen."""

    __tablename__ = "seen_variants"
    __table_args__ = (
        Index("idx_seen_variants_product", "product_id"),
    )

    variant_key: Mapped[str] = mapped_column(Text, primary_key=True)
    product_id: Mapped[str] = mapped_column(Text, nullable=False)
    color_code: Mapped[str] = mapped_column(Text, nullable=False)
    size_code: Mapped[str] = mapped_column(Text, nullable=False)
    discount_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class CheckHistory(Base):
    """One row per check run — feeds the status display and the heatmap."""

    __tablename__ = "check_history"
    __table_args__ = (
        Index("idx_check_history_ran_at", "ran_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    deals_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deals_matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deep_discounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DealObservation(Base):
    """Granular per-deal observation — the heatmap aggregates this table."""

    __tablename__ = "deal_observations"
    __table_args__ = (
        Index("idx_deal_observations_observed_at", "observed_at"),
        Index("idx_deal_observations_is_deep", "is_deep"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    product_id: Mapped[str] = mapped_column(Text, nullable=False)
    discount_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_deep: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class NotificationLog(Base):
    """Notification dispatch history — debugging plus the Inbox view."""

    __tablename__ = "notification_log"
    __table_args__ = (
        Index("idx_notification_log_sent_at", "sent_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    filter_ids: Mapped[list[int]] = mapped_column(JSONList, nullable=False, default=list)
    deal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MigrationApplied(Base):
    """Idempotency markers for one-shot data migrations (upstream import, etc.)."""

    __tablename__ = "migrations_applied"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class HealthProbe(Base):
    """Dedicated table the healthcheck writes to and immediately deletes from."""

    __tablename__ = "_health_probe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    probed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
