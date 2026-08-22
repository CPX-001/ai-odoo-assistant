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
    ContextReadTurnResponse,
    DelegationClaims,
    OdooGatewayReference,
)
from odoo_ai.contracts.effective_schema import (
    EffectiveFieldSchema,
    EffectiveModelSchema,
    EffectiveSelectionOption,
)
from odoo_ai.contracts.evidence import Evidence
from odoo_ai.contracts.explain import ExplainTurnRequest, ExplainTurnResponse
from odoo_ai.contracts.logs import LogEvidence, LogSearchRequest, TimestampRange
from odoo_ai.contracts.records import RecordRef, RecordSnapshot
from odoo_ai.contracts.screen_context import ScreenContext
from odoo_ai.contracts.source import (
    InstanceInventory,
    ManifestMetadata,
    ScanRun,
    SourceFile,
    SourceRef,
    SourceSymbol,
    XmlRecord,
)

type JsonSchema = dict[str, JsonValue]

PUBLIC_CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    AnswerEnvelope,
    ContextPack,
    ContextReadTurnRequest,
    ContextReadTurnResponse,
    ConversationState,
    Evidence,
    EffectiveFieldSchema,
    EffectiveModelSchema,
    EffectiveSelectionOption,
    ExplainTurnRequest,
    ExplainTurnResponse,
    DelegationClaims,
    InstanceInventory,
    InstanceProfileSummary,
    LogEvidence,
    LogSearchRequest,
    ManifestMetadata,
    OdooGatewayReference,
    ProposedAction,
    RecordRef,
    RecordSnapshot,
    ScreenContext,
    ScanRun,
    SourceFile,
    SourceRef,
    SourceSymbol,
    TimestampRange,
    ToolSpec,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
    XmlRecord,
)


def export_public_json_schemas() -> dict[str, JsonSchema]:
    """Return public contract schemas ordered by contract name."""

    return {
        model.__name__: cast(JsonSchema, model.model_json_schema())
        for model in sorted(PUBLIC_CONTRACT_MODELS, key=lambda contract: contract.__name__)
    }
