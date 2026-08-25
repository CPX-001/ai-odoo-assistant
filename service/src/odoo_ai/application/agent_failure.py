"""Host-owned fallback for unified-agent failures."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from odoo_ai.application.agent_policy import intersect_agent_policy
from odoo_ai.contracts import (
    AgentPlanMetadata,
    AgentPlanView,
    AgentPolicyView,
    AgentTurnRequest,
    AgentTurnResponse,
    AnswerConfidence,
    PlanState,
    RiskLevel,
)


def agent_failure_answer(code: str) -> str:
    """Return a short fallback only when a richer Codex diagnosis is unavailable."""

    normalized = str(code).casefold()
    if any(
        marker in normalized
        for marker in ("access_denied", "scope_denied", "permission")
    ):
        return (
            "No he podido continuar porque Odoo no me ha permitido acceder a algo que necesitaba. "
            "No he hecho ningún cambio. Si ese acceso debería estar permitido, habrá que revisar "
            "los permisos de tu usuario."
        )
    if any(marker in normalized for marker in ("timeout", "deadline")):
        return (
            "La petición se ha quedado sin tiempo antes de terminar. No he dado nada por hecho ni "
            "por aplicado. Puedes reintentarlo; si vuelve a pasar con una petición sencilla, habrá "
            "que revisar qué parte está tardando demasiado."
        )
    if any(marker in normalized for marker in ("budget", "limit", "repeated")):
        return (
            "He tenido que parar antes de terminar porque el proceso entró en demasiadas "
            "comprobaciones o intentos. No he dado la petición por completada. Puedes reintentarlo "
            "una vez; si se repite, habrá que revisar por qué se está atascando."
        )
    if any(marker in normalized for marker in ("evidence", "source", "knowledge")):
        return (
            "No he encontrado información suficiente para darte una respuesta fiable y prefiero no "
            "inventarla. No he dado nada por completado. Si vuelve a ocurrir, habrá que comprobar "
            "que la información que usa el Assistant esté disponible y actualizada."
        )
    if any(
        marker in normalized
        for marker in ("invalid_context", "model_unavailable", "context_mismatch")
    ):
        return (
            "No he podido identificar con suficiente seguridad a qué datos u objeto se refería la "
            "petición. No necesitas abrir una pantalla concreta para darme acceso; puedes "
            "reintentarlo indicando el concepto o registro con un poco más de precisión."
        )
    if any(
        marker in normalized
        for marker in (
            "codex",
            "engine_unavailable",
            "agent_unavailable",
            "runtime_not",
            "runtime_start",
            "authentication",
        )
    ):
        return (
            "No he podido terminar esta petición porque el sistema que la analiza no estaba "
            "disponible. En este caso tampoco puedo darte una causa más concreta sin inventarla. "
            "No he hecho ningún cambio. Puedes reintentarlo; si se repite, habrá que revisar el "
            "estado interno del Assistant."
        )
    return (
        "No he podido completar la petición de forma fiable. No tengo suficiente información para "
        "afirmar la causa y no voy a inventarla. No he dado nada por completado."
    )


def agent_failure_response(
    request: AgentTurnRequest,
    code: str,
    *,
    completed_at: datetime | None = None,
    answer_markdown: str | None = None,
    confidence: AnswerConfidence = AnswerConfidence.LOW,
) -> AgentTurnResponse:
    """Return a non-executable failed turn with an optional evidence-backed explanation."""

    policy = intersect_agent_policy(request.policy_layers)
    policy_view = AgentPolicyView(
        confirmation_mode=policy.confirmation_mode,
        max_auto_risk=policy.max_auto_risk,
        allow_synthetic_data=policy.allow_synthetic_data,
        constrained_by=policy.constrained_by,
    )
    plan = AgentPlanView(
        plan_id=uuid4(),
        state=PlanState.FAILED,
        risk=RiskLevel.LOW,
        metadata=AgentPlanMetadata(
            needs_read=False,
            needs_schema=False,
            needs_write=False,
            needs_business_action=False,
            has_external_effect=False,
            has_irreversible_effect=False,
            is_atomic=True,
            estimated_blast_radius=0,
        ),
        policy=policy_view,
        goal="Explicar por qué no se pudo completar la petición.",
        assumptions=(),
        steps=(),
        requires_confirmation=False,
        expires_at=None,
    )
    answer = (answer_markdown or "").strip() or agent_failure_answer(code)
    return AgentTurnResponse(
        turn_id=request.turn_id,
        conversation_id=request.conversation_id,
        state=PlanState.FAILED,
        answer_markdown=answer,
        confidence=confidence,
        plan=plan,
        completed_at=(completed_at or datetime.now(UTC)).astimezone(UTC),
    )
