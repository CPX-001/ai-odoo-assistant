"""Deterministic JSON Schema export for the residual service contract surface."""

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
from odoo_ai.contracts.delegation import ContextReadTurnRequest, ContextReadTurnResponse
from odoo_ai.contracts.effective_schema import (
    EffectiveFieldSchema,
    EffectiveModelSchema,
    EffectiveSelectionOption,
)
from odoo_ai.contracts.evidence import Evidence
from odoo_ai.contracts.explain import ExplainTurnRequest, ExplainTurnResponse
from odoo_ai.contracts.how_to import HowToTurnRequest, HowToTurnResponse
from odoo_ai.contracts.knowledge import (
    KnowledgeDocument,
    KnowledgeExcerpt,
    KnowledgeProviderIssue,
    KnowledgeReadExcerptRequest,
    KnowledgeRef,
    KnowledgeScanMetrics,
    KnowledgeScanResult,
    KnowledgeSearchCandidate,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)
from odoo_ai.contracts.logs import LogEvidence, LogSearchRequest, TimestampRange
from odoo_ai.contracts.navigation import (
    NavigationActionSummary,
    NavigationLimits,
    NavigationNode,
    NavigationSnapshot,
)
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

JsonSchema = dict[str, JsonValue]

_PUBLIC_MODELS: tuple[type[BaseModel], ...] = (
    AnswerEnvelope,
    ContextPack,
    ContextReadTurnRequest,
    ContextReadTurnResponse,
    ConversationState,
    EffectiveFieldSchema,
    EffectiveModelSchema,
    EffectiveSelectionOption,
    Evidence,
    ExplainTurnRequest,
    ExplainTurnResponse,
    HowToTurnRequest,
    HowToTurnResponse,
    InstanceInventory,
    InstanceProfileSummary,
    KnowledgeDocument,
    KnowledgeExcerpt,
    KnowledgeProviderIssue,
    KnowledgeReadExcerptRequest,
    KnowledgeRef,
    KnowledgeScanMetrics,
    KnowledgeScanResult,
    KnowledgeSearchCandidate,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    LogEvidence,
    LogSearchRequest,
    ManifestMetadata,
    NavigationActionSummary,
    NavigationLimits,
    NavigationNode,
    NavigationSnapshot,
    ProposedAction,
    RecordRef,
    RecordSnapshot,
    ScanRun,
    ScreenContext,
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
    """Return stable schemas for contracts still exposed by the service."""

    return {
        model.__name__: model.model_json_schema()
        for model in sorted(_PUBLIC_MODELS, key=lambda item: item.__name__)
    }
