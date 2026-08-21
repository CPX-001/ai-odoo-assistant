"""Deterministic JSON Schema export for public M0 contracts."""

from typing import cast

from pydantic import BaseModel, JsonValue

from odoo_ai.contracts.agent import AnswerEnvelope, ProposedAction, ToolSpec
from odoo_ai.contracts.context import (
    ContextPack,
    ConversationState,
    InstanceProfileSummary,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
)
from odoo_ai.contracts.delegation import (
    ContextReadTurnRequest,
    DelegationClaims,
    OdooGatewayReference,
)
from odoo_ai.contracts.evidence import Evidence
from odoo_ai.contracts.logs import LogEvidence, LogSearchRequest, TimestampRange
from odoo_ai.contracts.records import RecordRef, RecordSnapshot
from odoo_ai.contracts.screen_context import ScreenContext

type JsonSchema = dict[str, JsonValue]

PUBLIC_CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    AnswerEnvelope,
    ContextPack,
    ContextReadTurnRequest,
    ConversationState,
    Evidence,
    DelegationClaims,
    InstanceProfileSummary,
    LogEvidence,
    LogSearchRequest,
    OdooGatewayReference,
    ProposedAction,
    RecordRef,
    RecordSnapshot,
    ScreenContext,
    TimestampRange,
    ToolSpec,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
)


def export_public_json_schemas() -> dict[str, JsonSchema]:
    """Return public contract schemas ordered by contract name."""

    return {
        model.__name__: cast(JsonSchema, model.model_json_schema())
        for model in sorted(PUBLIC_CONTRACT_MODELS, key=lambda contract: contract.__name__)
    }
