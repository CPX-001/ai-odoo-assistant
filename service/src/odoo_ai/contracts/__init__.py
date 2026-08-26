"""Public contracts for the responsibilities still hosted by the temporary service."""

from odoo_ai.contracts.agent import (
    AnswerConfidence,
    AnswerEnvelope,
    ProposedAction,
    ToolRisk,
    ToolSpec,
)
from odoo_ai.contracts.content_source import ContentSourceDescriptor, Fingerprint
from odoo_ai.contracts.context import (
    ContextPack,
    ConversationState,
    InstanceProfileSummary,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
    Workflow,
)
from odoo_ai.contracts.delegation import (
    ContextReadTurnRequest,
    ContextReadTurnResponse,
    DelegationClaims,
    DelegationScope,
    OdooGatewayReference,
)
from odoo_ai.contracts.diagnostics import (
    DiagnosticCapability,
    DiagnosticCapabilityStatus,
    DiagnosticSnapshot,
    DiagnosticsResponse,
)
from odoo_ai.contracts.effective_schema import (
    EffectiveFieldSchema,
    EffectiveModelSchema,
    EffectiveSelectionOption,
)
from odoo_ai.contracts.evidence import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
)
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
from odoo_ai.contracts.logs import (
    LogCorrelation,
    LogEvidence,
    LogSearchRequest,
    TimestampRange,
)
from odoo_ai.contracts.navigation import (
    NavigationActionSummary,
    NavigationLimits,
    NavigationNode,
    NavigationSnapshot,
)
from odoo_ai.contracts.records import RecordRef, RecordSnapshot
from odoo_ai.contracts.schema import JsonSchema, export_public_json_schemas
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
from odoo_ai.contracts.tool_execution import ToolExecutionResult

__all__ = [
    "AnswerConfidence",
    "AnswerEnvelope",
    "ContentSourceDescriptor",
    "ContextPack",
    "ContextReadTurnRequest",
    "ContextReadTurnResponse",
    "ConversationState",
    "DelegationClaims",
    "DelegationScope",
    "DiagnosticCapability",
    "DiagnosticCapabilityStatus",
    "DiagnosticSnapshot",
    "DiagnosticsResponse",
    "EffectiveFieldSchema",
    "EffectiveModelSchema",
    "EffectiveSelectionOption",
    "Evidence",
    "EvidenceKind",
    "EvidenceSensitivity",
    "EvidenceStatus",
    "ExplainTurnRequest",
    "ExplainTurnResponse",
    "Fingerprint",
    "InstanceInventory",
    "InstanceProfileSummary",
    "JsonSchema",
    "KnowledgeDocument",
    "KnowledgeExcerpt",
    "KnowledgeProviderIssue",
    "KnowledgeReadExcerptRequest",
    "KnowledgeRef",
    "KnowledgeScanMetrics",
    "KnowledgeScanResult",
    "KnowledgeSearchCandidate",
    "KnowledgeSearchRequest",
    "KnowledgeSearchResult",
    "LogCorrelation",
    "LogEvidence",
    "LogSearchRequest",
    "ManifestMetadata",
    "NavigationActionSummary",
    "NavigationLimits",
    "NavigationNode",
    "NavigationSnapshot",
    "OdooGatewayReference",
    "ProposedAction",
    "RecordRef",
    "RecordSnapshot",
    "ScanRun",
    "ScreenContext",
    "SourceFile",
    "SourceRef",
    "SourceSymbol",
    "TimestampRange",
    "ToolExecutionResult",
    "ToolRisk",
    "ToolSpec",
    "TurnLimits",
    "UserExecutionContext",
    "UserRequest",
    "Workflow",
    "XmlRecord",
    "export_public_json_schemas",
]
