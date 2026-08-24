"""Source-neutral provenance for content that may feed Assistant workflows.

The descriptor identifies an upstream object without embedding its bytes, extracted
text, credentials or host filesystem path. Provider adapters own how a reference is
resolved (for example an Odoo attachment id or an Assistant-managed upload id).
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from odoo_ai.contracts.action import Fingerprint

ContentProvider = Annotated[
    str,
    Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$"),
]


class ContentSourceDescriptor(BaseModel):
    """Stable provenance pointer with no transport- or parser-specific payload."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider: ContentProvider
    reference: str = Field(min_length=1, max_length=512)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    media_type: str | None = Field(default=None, min_length=3, max_length=127)
    content_fingerprint: Fingerprint | None = None

    @field_validator("reference", "display_name", "media_type")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("content source text is invalid")
        return value

    @model_validator(mode="after")
    def validate_media_type(self) -> Self:
        if self.media_type is not None:
            if (
                self.media_type != self.media_type.lower()
                or "/" not in self.media_type
                or self.media_type.startswith("/")
                or self.media_type.endswith("/")
                or " " in self.media_type
            ):
                raise ValueError("content source media type is invalid")
        return self
