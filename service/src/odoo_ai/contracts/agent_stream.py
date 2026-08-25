"""Provider-neutral events emitted while one unified agent turn is running."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from odoo_ai.contracts.agent_turn import AgentTurnResponse


class AgentTurnDeltaEvent(BaseModel):
    """Provisional user-visible answer text; it never carries plan or authority data."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    type: Literal["delta"] = "delta"
    text: Annotated[str, Field(min_length=1, max_length=4096)]


class AgentTurnFinalEvent(BaseModel):
    """Host-validated terminal response for the turn."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    type: Literal["final"] = "final"
    response: AgentTurnResponse


AgentTurnEvent: TypeAlias = AgentTurnDeltaEvent | AgentTurnFinalEvent
