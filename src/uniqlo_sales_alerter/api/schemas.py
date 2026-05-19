"""Request and response schemas for the fork-foundation REST endpoints.

The schemas validate inbound JSON and shape outbound responses for the new
``/api/v1/filters`` and ``/ui/filters`` routes. The matcher still runs against
``config.yaml``'s legacy single filter for the foundation phase — these rows
sit in SQLite without driving notifications until step 8 swaps the matcher
onto them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_VALID_GENDERS: frozenset[str] = frozenset({"men", "women", "unisex", "kids", "baby"})
_VALID_AVAILABILITY: frozenset[str] = frozenset({"online", "in_store", "both"})


class SavedFilterBase(BaseModel):
    """Shared fields for create and update payloads."""

    name: str = Field(min_length=1, max_length=200)
    gender: list[str] = Field(default_factory=list)
    min_discount: float = Field(default=0.0, ge=0.0, le=100.0)
    sizes_clothing: list[str] = Field(default_factory=list)
    sizes_pants: list[str] = Field(default_factory=list)
    sizes_shoes: list[str] = Field(default_factory=list)
    one_size_match: bool = False
    availability_mode: Literal["online", "in_store", "both"] = "both"
    ignored_keywords: list[str] = Field(default_factory=list)
    enabled: bool = True
    snooze_until: datetime | None = None

    @field_validator("gender")
    @classmethod
    def _genders_valid(cls, value: list[str]) -> list[str]:
        invalid = [v for v in value if v.lower() not in _VALID_GENDERS]
        if invalid:
            raise ValueError(
                f"invalid gender values: {invalid}; expected subset of {sorted(_VALID_GENDERS)}"
            )
        return [v.lower() for v in value]

    @field_validator("name")
    @classmethod
    def _name_stripped(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned


class SavedFilterCreate(SavedFilterBase):
    """Payload accepted by ``POST /api/v1/filters``."""


class SavedFilterUpdate(SavedFilterBase):
    """Payload accepted by ``PUT /api/v1/filters/{id}``.

    Same fields as create — partial updates are not supported in v1 to keep
    the matcher diff simple. Clients send the whole filter.
    """


class SavedFilterRead(SavedFilterBase):
    """Response shape returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
