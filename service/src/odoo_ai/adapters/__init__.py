"""Infrastructure adapters for residual Source/Retrieval/Diagnostics responsibilities."""

from odoo_ai.adapters.codex_runtime import (
    APP_SERVER_PROTOCOL,
    CodexAppServerClient,
    CodexProbeState,
    CodexProtocolError,
    CodexRuntimeConfigurationError,
    CodexRuntimeError,
    CodexRuntimeNotFoundError,
    CodexRuntimeProbe,
    CodexRuntimeProcessError,
    CodexRuntimeTimeoutError,
    CodexServerInfo,
    CodexThreadPolicy,
    probe_codex_readiness,
    probe_codex_runtime,
)
from odoo_ai.adapters.codex_status import CachedCodexReasoningStatus
from odoo_ai.adapters.configured_codex import (
    ConfiguredCodexRuntimeSettings as CodexRuntimeSettings,
)
from odoo_ai.adapters.configured_diagnostics import (
    ConfiguredRuntimeDiagnosticsService as RuntimeDiagnosticsService,
)
from odoo_ai.adapters.knowledge_tools import (
    KNOWLEDGE_READ_EXCERPT,
    KNOWLEDGE_SEARCH,
    KnowledgeReadExcerptToolData,
    KnowledgeToolBackend,
    KnowledgeToolExecutorFactory,
    RuntimeKnowledgeToolBackend,
    build_knowledge_tool_registry,
    knowledge_tool_specs,
)
from odoo_ai.adapters.odoo_http import (
    HttpOdooInstanceGateway,
    OdooGatewayFactory,
    OdooGatewaySettings,
)
from odoo_ai.adapters.source_tools import (
    SOURCE_FIND_MODEL_EXTENSIONS,
    SOURCE_FIND_SYMBOL,
    SOURCE_READ_EXCERPT,
    ReadExcerptToolData,
    RuntimeSourceToolBackend,
    SourceToolBackend,
    SourceToolExecutorFactory,
    build_source_tool_registry,
    source_tool_specs,
)
from odoo_ai.ports import OdooGatewayError

__all__ = [
    "APP_SERVER_PROTOCOL",
    "CachedCodexReasoningStatus",
    "CodexAppServerClient",
    "CodexProbeState",
    "CodexProtocolError",
    "CodexRuntimeConfigurationError",
    "CodexRuntimeError",
    "CodexRuntimeNotFoundError",
    "CodexRuntimeProbe",
    "CodexRuntimeProcessError",
    "CodexRuntimeSettings",
    "CodexRuntimeTimeoutError",
    "CodexServerInfo",
    "CodexThreadPolicy",
    "HttpOdooInstanceGateway",
    "KNOWLEDGE_READ_EXCERPT",
    "KNOWLEDGE_SEARCH",
    "KnowledgeReadExcerptToolData",
    "KnowledgeToolBackend",
    "KnowledgeToolExecutorFactory",
    "OdooGatewayError",
    "OdooGatewayFactory",
    "OdooGatewaySettings",
    "ReadExcerptToolData",
    "RuntimeDiagnosticsService",
    "RuntimeKnowledgeToolBackend",
    "RuntimeSourceToolBackend",
    "SOURCE_FIND_MODEL_EXTENSIONS",
    "SOURCE_FIND_SYMBOL",
    "SOURCE_READ_EXCERPT",
    "SourceToolBackend",
    "SourceToolExecutorFactory",
    "build_knowledge_tool_registry",
    "build_source_tool_registry",
    "knowledge_tool_specs",
    "probe_codex_readiness",
    "probe_codex_runtime",
    "source_tool_specs",
]
