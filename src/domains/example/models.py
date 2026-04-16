from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class Item(BaseModel):
    """
    Persisted item representation.

    SOC 2 CC6/CC8: Every record carries a full provenance trail — who created
    it, who last modified it, and when — so that access and change events can be
    reconstructed during an audit.
    """

    id: str
    name: str
    data: dict[str, Any] = Field(default_factory=dict)
    # Provenance: set by the service layer from the authenticated principal (ctx).
    # Nullable because the example runs without mandatory auth; real services
    # should make these non-nullable once an auth provider is wired.
    created_by: str | None = None
    updated_by: str | None = None
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
