"""Short-lived authority for one exact idempotent batch chunk."""

from __future__ import annotations

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from odoo_ai.contracts.action import Fingerprint, Revision
from odoo_ai.contracts.batch import BatchFailureMode, BatchMutationKind


class BatchAuthorityClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal[1] = 1
    jti: str = Field(pattern=r"^[A-Za-z0-9_-]{22,64}$")
    job_id: UUID
    attempt_id: UUID
    authorization_id: UUID
    job_fingerprint: Fingerprint
    chunk_fingerprint: Fingerprint
    instance_id: str = Field(min_length=1, max_length=255)
    database: str = Field(min_length=1, max_length=128)
    uid: int = Field(strict=True, gt=0)
    company_id: int = Field(strict=True, gt=0)
    allowed_company_ids: tuple[int, ...] = Field(min_length=1, max_length=16)
    operation: BatchMutationKind
    model: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
    schema_id: Fingerprint | None = None
    fields: tuple[str, ...] = Field(default=(), max_length=16)
    failure_mode: BatchFailureMode
    policy_revision: Revision
    row_count: int = Field(strict=True, ge=1, le=200)
    scopes: tuple[Literal["batch_commit"], ...] = ("batch_commit",)
    issued_at: int = Field(strict=True, ge=0)
    expires_at: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def validate_closed_authority(self) -> Self:
        write = self.operation in {BatchMutationKind.CREATE, BatchMutationKind.PATCH}
        if (
            self.database != self.database.strip()
            or any(ord(character) < 32 for character in self.database)
            or self.instance_id != self.instance_id.strip()
            or any(ord(character) < 32 for character in self.instance_id)
            or self.allowed_company_ids != tuple(sorted(set(self.allowed_company_ids)))
            or self.company_id not in self.allowed_company_ids
            or self.fields != tuple(sorted(set(self.fields)))
            or any(
                not field
                or len(field) > 128
                or not field[0].isalpha() and field[0] != "_"
                or any(not (character.isalnum() or character == "_") for character in field)
                for field in self.fields
            )
            or self.scopes != ("batch_commit",)
            or not self.job_fingerprint.startswith("batch-job:v1:sha256:")
            or not self.chunk_fingerprint.startswith("batch-chunk:v1:sha256:")
            or (write and (self.schema_id is None or not self.fields))
            or (self.operation is BatchMutationKind.DELETE and (self.schema_id is not None or self.fields))
        ):
            raise ValueError("invalid batch authority")
        return self
