"""Sanitized operation outcomes shared by typed broker families."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OperationOutcome:
    status: str = "ok"
    effect_state: str = "none"
    summary: dict[str, Any] = field(default_factory=dict)
    precondition_fingerprint: str | None = None
    postcondition_fingerprint: str | None = None
    recovery_classification: str = "none"
    recovery_token: str | None = None
    error_code: str | None = None


class BrokerOperationError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        status: str = "denied",
        effect_state: str = "none",
        summary: dict[str, Any] | None = None,
        precondition_fingerprint: str | None = None,
        postcondition_fingerprint: str | None = None,
        recovery_classification: str = "none",
        recovery_token: str | None = None,
    ) -> None:
        super().__init__(code)
        self.outcome = OperationOutcome(
            status=status,
            effect_state=effect_state,
            summary=summary or {},
            precondition_fingerprint=precondition_fingerprint,
            postcondition_fingerprint=postcondition_fingerprint,
            recovery_classification=recovery_classification,
            recovery_token=recovery_token,
            error_code=code,
        )


__all__ = ["BrokerOperationError", "OperationOutcome"]
