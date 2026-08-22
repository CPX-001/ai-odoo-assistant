"""Host-controlled tool execution primitives."""

from odoo_ai.contracts import ToolExecutionEvent, ToolExecutionReport
from odoo_ai.tools.executor import (
    EvidenceLedger,
    EvidenceOrigin,
    RegisteredTool,
    ToolCall,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
    ToolHandlerOutput,
    ToolRegistry,
    ValidatedToolResult,
)

__all__ = [
    "EvidenceLedger",
    "EvidenceOrigin",
    "RegisteredTool",
    "ToolCall",
    "ToolExecutionLimits",
    "ToolExecutionEvent",
    "ToolExecutionReport",
    "ToolExecutor",
    "ToolExecutorError",
    "ToolHandlerOutput",
    "ToolRegistry",
    "ValidatedToolResult",
]
