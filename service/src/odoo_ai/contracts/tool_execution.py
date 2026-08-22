"""Provider-neutral metadata emitted by one bounded tool execution turn."""

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import JsonValue

from odoo_ai.contracts.evidence import Evidence


@dataclass(frozen=True, slots=True)
class ToolExecutionEvent:
    """One metadata-only tool event safe to copy into a logical trace."""

    event_name: str
    status: str
    attributes: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ToolExecutionReport:
    """Evidence and sanitized events produced by one closed tool executor."""

    events: tuple[ToolExecutionEvent, ...] = ()
    retrieved_evidence: tuple[Evidence, ...] = ()
