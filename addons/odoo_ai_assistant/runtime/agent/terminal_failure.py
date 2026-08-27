"""Project terminal host/queue failures into the bounded FailureEnvelope contract."""

from __future__ import annotations

from dataclasses import dataclass
import re
import secrets

from .failure import FailureEnvelope, FailureEnvelopeError

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


@dataclass(frozen=True, slots=True)
class _TerminalRoute:
    category: str
    stage: str
    component: str
    retryability: str
    user_action: str
    safe_summary: str


_EXACT_ROUTES = {
    "access_denied": _TerminalRoute(
        "odoo_access",
        "runtime",
        "odoo",
        "after_change",
        "request_access",
        "Odoo denegó el acceso necesario para completar la petición.",
    ),
    "runtime_unavailable": _TerminalRoute(
        "queue_worker",
        "runtime",
        "queue",
        "unknown",
        "retry",
        "El runtime del Assistant no pudo completar la petición.",
    ),
    "worker_lost": _TerminalRoute(
        "queue_worker",
        "queue",
        "queue",
        "safe",
        "retry",
        "El worker que procesaba la petición dejó de estar disponible.",
    ),
    "worker_lost_after_write_barrier": _TerminalRoute(
        "queue_worker",
        "execution",
        "queue",
        "never",
        "review",
        "El worker se perdió después de cruzar el límite de escritura.",
    ),
    "agent_turn_lease_lost": _TerminalRoute(
        "queue_worker",
        "queue",
        "queue",
        "unknown",
        "review",
        "El worker perdió la autoridad sobre la petición en curso.",
    ),
    "agent_working_transcript_persist_failed": _TerminalRoute(
        "persistence",
        "persistence",
        "odoo",
        "unknown",
        "review",
        "No se pudo persistir el estado interno seguro de la petición.",
    ),
    "capability_verification_failed": _TerminalRoute(
        "verification",
        "verification",
        "capability",
        "never",
        "review",
        "La verificación del resultado de la operación no pudo completarse.",
    ),
    "capability_plan_approval_required": _TerminalRoute(
        "approval",
        "approval",
        "capability",
        "after_change",
        "review",
        "La operación requiere una aprobación que no estaba disponible.",
    ),
    "capability_plan_not_authorized": _TerminalRoute(
        "approval",
        "approval",
        "capability",
        "after_change",
        "review",
        "La operación no estaba autorizada para ejecutarse.",
    ),
    "capability_authority_mismatch": _TerminalRoute(
        "policy",
        "policy",
        "capability",
        "never",
        "review",
        "La capacidad solicitada no coincidió con la autoridad permitida.",
    ),
    "capability_policy_denied": _TerminalRoute(
        "policy",
        "policy",
        "capability",
        "after_change",
        "review",
        "La política del Assistant bloqueó la operación solicitada.",
    ),
    "capability_not_available": _TerminalRoute(
        "capability_discovery",
        "capability",
        "capability",
        "after_change",
        "review",
        "La capacidad necesaria no está disponible en esta instancia.",
    ),
    "capability_not_registered": _TerminalRoute(
        "capability_discovery",
        "capability",
        "capability",
        "after_change",
        "review",
        "La capacidad solicitada no está registrada en esta instancia.",
    ),
}


def terminal_failure_envelope(
    error: object,
    *,
    error_code: str,
    write_barrier: bool,
    diagnostic_id: str | None = None,
) -> FailureEnvelope:
    """Return one validated terminal envelope using queue effect authority."""

    if (
        not isinstance(error_code, str)
        or _CODE_RE.fullmatch(error_code) is None
        or type(write_barrier) is not bool
    ):
        raise FailureEnvelopeError()

    carried = getattr(error, "failure", None)
    if isinstance(carried, FailureEnvelope) and carried.code == error_code:
        base = carried
    else:
        route = _route_for_code(error_code)
        base = FailureEnvelope(
            code=error_code,
            category=route.category,
            stage=route.stage,
            component=route.component,
            retryability=route.retryability,
            effect_state="none",
            user_action=route.user_action,
            safe_summary=route.safe_summary,
            safe_details={},
            diagnostic_id=diagnostic_id or _new_diagnostic_id(),
            provider_code=None,
        )

    if write_barrier:
        return FailureEnvelope(
            code=base.code,
            category=base.category,
            stage=base.stage,
            component=base.component,
            retryability="never",
            effect_state="unknown",
            user_action="review",
            safe_summary=base.safe_summary,
            safe_details=dict(base.safe_details),
            diagnostic_id=base.diagnostic_id,
            provider_code=base.provider_code,
        )

    if base.effect_state == "none":
        return base
    return FailureEnvelope(
        code=base.code,
        category=base.category,
        stage=base.stage,
        component=base.component,
        retryability=base.retryability,
        effect_state="none",
        user_action=base.user_action,
        safe_summary=base.safe_summary,
        safe_details=dict(base.safe_details),
        diagnostic_id=base.diagnostic_id,
        provider_code=base.provider_code,
    )


def _route_for_code(code: str) -> _TerminalRoute:
    exact = _EXACT_ROUTES.get(code)
    if exact is not None:
        return exact

    if code == "agent_cancelled":
        return _TerminalRoute(
            "cancellation",
            "cancellation",
            "queue",
            "never",
            "none",
            "La petición fue cancelada antes de completarse.",
        )
    if code.startswith("codex_"):
        if any(
            token in code
            for token in ("timeout", "process_", "runtime_start", "stdout_unavailable")
        ):
            return _TerminalRoute(
                "provider_connection",
                "provider",
                "codex",
                "unknown",
                "retry",
                "La conexión con el proveedor de razonamiento no pudo completarse.",
            )
        if any(token in code for token in ("answer_", "output_", "turn_items")):
            return _TerminalRoute(
                "provider_output",
                "provider",
                "codex",
                "never",
                "review",
                "La salida del proveedor no pudo validarse con el contrato esperado.",
            )
        return _TerminalRoute(
            "provider_protocol",
            "provider",
            "codex",
            "never",
            "review",
            "La respuesta del proveedor no cumplió el protocolo esperado.",
        )
    if code.startswith(
        ("capability_input_", "agent_capability_arguments_", "agent_plan_arguments_")
    ):
        return _TerminalRoute(
            "capability_input",
            "capability",
            "capability",
            "after_change",
            "clarify",
            "Los datos solicitados para la capacidad no cumplen su contrato.",
        )
    if code.startswith(("capability_output_", "agent_capability_result_")):
        return _TerminalRoute(
            "capability_output",
            "capability",
            "capability",
            "unknown",
            "review",
            "El resultado de la capacidad no cumplió su contrato.",
        )
    if code.startswith(("capability_", "agent_capability_")):
        return _TerminalRoute(
            "capability_execution",
            "capability",
            "capability",
            "unknown",
            "review",
            "La capacidad necesaria no pudo completar su ejecución.",
        )
    if code.startswith("retrieval_"):
        return _TerminalRoute(
            "retrieval",
            "retrieval",
            "retrieval",
            "unknown",
            "retry",
            "La recuperación de contexto no pudo completarse.",
        )
    if code.startswith(("agent_message_", "agent_history_")):
        return _TerminalRoute(
            "input",
            "input",
            "odoo",
            "after_change",
            "clarify",
            "La petición no pudo validarse con el contrato de entrada.",
        )
    if code.startswith(("agent_context_", "codex_context_")):
        return _TerminalRoute(
            "context",
            "context",
            "odoo",
            "after_change",
            "clarify",
            "El contexto de la petición no pudo procesarse de forma segura.",
        )
    return _TerminalRoute(
        "internal",
        "runtime",
        "odoo",
        "unknown",
        "review",
        "El Assistant no pudo completar la petición.",
    )


def _new_diagnostic_id() -> str:
    return f"diag-{secrets.token_hex(12)}"
