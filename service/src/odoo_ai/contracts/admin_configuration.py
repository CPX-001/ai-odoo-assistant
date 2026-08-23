"""Internal M7 admin configuration request/response contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from odoo_ai.contracts.configuration import (
    AssistantAdminOverrides,
    EffectiveConfigSnapshot,
)


class AdminConfigurationActor(BaseModel):
    """Odoo-derived audit identity for one administrative configuration change."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    odoo_uid: int = Field(gt=0)
    odoo_database: str = Field(min_length=1, max_length=128, pattern=r"^[^\r\n\x00]+$")


class AdminConfigurationValidateRequest(BaseModel):
    """Closed validation request; arbitrary configuration keys are impossible."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overrides: AssistantAdminOverrides


class AdminConfigurationApplyRequest(BaseModel):
    """Revision-guarded apply request originating from the Odoo server."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_revision: int = Field(ge=0)
    overrides: AssistantAdminOverrides
    actor: AdminConfigurationActor


class AdminConfigurationAuthorized(BaseModel):
    """Sanitized host-owned envelopes/options relevant to mutable selectors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_roots: tuple[str, ...] = ()
    log_providers: tuple[Literal["auto", "file", "journal"], ...] = ("auto",)


class AdminConfigurationResponse(BaseModel):
    """Sanitized configuration state returned only over the machine-auth admin API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True] = True
    revision: int = Field(ge=0)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_state: Literal["valid", "invalid"]
    post_action: Literal["none", "restart_required", "setup_required"] = "none"
    overrides: AssistantAdminOverrides
    authorized: AdminConfigurationAuthorized
    snapshot: EffectiveConfigSnapshot
