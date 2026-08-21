"""Stable, transport-independent contracts for the Assistant Service."""

from odoo_ai.contracts.agent import (
    AnswerConfidence,
    AnswerEnvelope,
    ProposedAction,
    ToolRisk,
    ToolSpec,
)
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
    DELEGATION_FORMAT_VERSION,
    ContextReadTurnRequest,
    DelegationClaims,
    DelegationScope,
    OdooGatewayReference,
)
from odoo_ai.contracts.evidence import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
)
from odoo_ai.contracts.logs import (
    LogCorrelation,
    LogEvidence,
    LogSearchRequest,
    TimestampRange,
)
from odoo_ai.contracts.records import RecordRef, RecordSnapshot
from odoo_ai.contracts.schema import PUBLIC_CONTRACT_MODELS, export_public_json_schemas
from odoo_ai.contracts.screen_context import ScreenContext

__all__ = [
    "AnswerConfidence",
    "AnswerEnvelope",
    "ContextPack",
    "ConversationState",
    "ContextReadTurnRequest",
    "DELEGATION_FORMAT_VERSION",
    "DelegationClaims",
    "DelegationScope",
    "Evidence",
    "EvidenceKind",
    "EvidenceSensitivity",
    "EvidenceStatus",
    "InstanceProfileSummary",
    "LogCorrelation",
    "LogEvidence",
    "LogSearchRequest",
    "OdooGatewayReference",
    "ProposedAction",
    "PUBLIC_CONTRACT_MODELS",
    "RecordRef",
    "RecordSnapshot",
    "ScreenContext",
    "ToolRisk",
    "ToolSpec",
    "TimestampRange",
    "TurnLimits",
    "UserExecutionContext",
    "UserRequest",
    "Workflow",
    "export_public_json_schemas",
]
