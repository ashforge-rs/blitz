from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class Item(BaseModel):
    """Persisted item representation."""

    id: str
    name: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CreateItemRequest(BaseModel):
    """Payload accepted when creating a new item."""

    name: str = Field(min_length=1, max_length=255)
    data: dict[str, Any] = Field(default_factory=dict)


class UpdateItemRequest(BaseModel):
    """Payload accepted when updating an existing item.  All fields are optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    data: dict[str, Any] | None = None
