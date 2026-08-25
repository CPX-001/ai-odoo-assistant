"""Host-owned user-facing explanations for unified-agent failures."""

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
    """Explain a sanitized failure without exposing internal codes or stack details."""

    normalized = code.casefold()
    if any(marker in normalized for marker in ("access_denied", "scope_denied", "permission")):
        diagnosis = "Odoo ha rechazado parte del acceso necesario para completar la petición."
        reason = (
            "La operación se ejecuta con tu usuario real, por lo que se respetan sus permisos, "
            "reglas de registro, campos accesibles y compañías activas."
        )
        solution = (
            "No doy la operación por completada. Si deberías tener acceso, revisa los grupos, "
            "ACL, reglas de registro y compañías permitidas de ese usuario; si no, necesitarás "
            "que un administrador amplíe esos permisos."
        )
    elif any(marker in normalized for marker in ("timeout", "deadline")):
        diagnosis = "La petición no terminó dentro del tiempo seguro disponible."
        reason = (
            "El razonamiento o una de las comprobaciones necesarias tardó más que el límite "
            "configurado, así que el turno se detuvo antes de poder validar un resultado final."
        )
        solution = (
            "No doy la operación por completada. Puedes reintentarlo; si vuelve a ocurrir con una "
            "petición pequeña, conviene revisar Diagnostics y los tiempos del Assistant/Codex antes "
            "de aumentar el timeout."
        )
    elif any(marker in normalized for marker in ("budget", "limit", "repeated")):
        diagnosis = "El agente se atascó en una cadena de comprobaciones y activó un límite de seguridad."
        reason = (
            "Se alcanzó un límite de herramientas, intentos repetidos o presupuesto antes de "
            "obtener un resultado suficientemente fiable."
        )
        solution = (
            "No doy la operación por completada. Reintenta la misma petición una vez; si una "
            "operación sencilla vuelve a alcanzar este límite, debe tratarse como un problema del "
            "runtime y revisarse en Diagnostics, no como una limitación normal del usuario."
        )
    elif any(
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
        diagnosis = "El motor de razonamiento no estaba disponible para terminar este turno."
        reason = (
            "El Assistant no pudo iniciar o mantener una sesión válida con el motor antes de "
            "producir una respuesta verificable."
        )
        solution = (
            "No doy la operación por completada. Reintenta una vez; si persiste, revisa Diagnostics "
            "para comprobar el estado de Codex, su autenticación y el proceso App Server."
        )
    elif any(marker in normalized for marker in ("evidence", "source", "knowledge")):
        diagnosis = "No he podido reunir evidencia suficiente para responder con fiabilidad."
        reason = (
            "La fuente que debía verificar esa parte de la respuesta no estaba disponible o no "
            "pudo validarse en este turno."
        )
        solution = (
            "No voy a rellenar el hueco con una suposición. Si se trata de código o documentación, "
            "comprueba Source/Knowledge en Diagnostics y reindexa únicamente si esa fuente aparece "
            "desactualizada o sin indexar."
        )
    elif any(marker in normalized for marker in ("invalid_context", "model_unavailable", "context_mismatch")):
        diagnosis = "No he podido resolver de forma segura el contexto necesario para esta petición."
        reason = (
            "La información disponible no permitió vincular la petición con un modelo o contexto "
            "válido sin hacer una suposición insegura."
        )
        solution = (
            "No necesitas navegar a una pantalla concreta para darme acceso. Reintenta indicando el "
            "concepto o registro que buscas; si vuelve a pasar, debe revisarse la detección de modelos "
            "del agente."
        )
    elif any(marker in normalized for marker in ("plan_store", "approval_store", "store_unavailable")):
        diagnosis = "No he podido guardar de forma fiable el estado necesario para continuar la operación."
        reason = (
            "El almacenamiento del plan o de la aprobación no confirmó una persistencia válida, por "
            "lo que no es seguro continuar como si el estado se hubiera guardado."
        )
        solution = (
            "No continúes aprobando o repitiendo la operación hasta que el almacenamiento vuelva a "
            "estar disponible. Revisa Diagnostics y la conexión a la base de datos del Assistant."
        )
    else:
        diagnosis = "No he podido completar esta petición de forma verificable."
        reason = (
            "El turno se interrumpió antes de producir un resultado que el host pudiera validar con "
            "suficiente seguridad."
        )
        solution = (
            "No doy la operación por completada. Puedes reintentarlo; si vuelve a ocurrir, revisa "
            "Diagnostics para localizar el componente que está fallando."
        )
    return (
        f"**Diagnóstico.** {diagnosis}\n\n"
        f"**Motivo.** {reason}\n\n"
        f"**Solución.** {solution}"
    )


def agent_failure_response(
    request: AgentTurnRequest,
    code: str,
    *,
    completed_at: datetime | None = None,
) -> AgentTurnResponse:
    """Return a non-executable failed turn for browser compatibility and useful UX."""

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
    return AgentTurnResponse(
        turn_id=request.turn_id,
        conversation_id=request.conversation_id,
        state=PlanState.FAILED,
        answer_markdown=agent_failure_answer(code),
        confidence=AnswerConfidence.LOW,
        plan=plan,
        completed_at=(completed_at or datetime.now(UTC)).astimezone(UTC),
    )
