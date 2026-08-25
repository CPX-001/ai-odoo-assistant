"""Conversational fallback for browser-visible chat failures."""

from __future__ import annotations

from uuid import UUID, uuid4

from odoo import api, models


class AssistantChatFailureBridge(models.AbstractModel):
    _inherit = "odoo.ai.assistant.bridge"

    @api.model
    def submit_chat(self, message, screen, conversation_id=None):
        """Render expected failures as normal Assistant messages, never raw browser errors."""

        result = super().submit_chat(message, screen, conversation_id=conversation_id)
        if not isinstance(result, dict) or result.get("ok") is not False:
            return result
        failure = _failure_chat_result(
            self,
            code=_error_code(result),
            message=message,
            conversation_id=conversation_id,
        )
        normalized_message = _safe_message(message)
        if not normalized_message:
            return failure
        try:
            return self._persist_chat_result(
                failure,
                message=normalized_message,
                conversation_id=_safe_conversation_id(conversation_id),
                internal_workflow="AGENT_FAILURE",
            )
        except Exception:  # noqa: BLE001 - the diagnostic must survive history failures
            return failure


def _failure_chat_result(bridge, *, code, message, conversation_id):
    return {
        "ok": True,
        "turn_id": str(uuid4()),
        "workflow": "AGENT",
        "answer": _failure_answer(code),
        "confidence": "low",
        "limitations": [],
        "citations": [],
        "plan": _failure_plan(bridge, message, conversation_id),
        "conversation_id": _safe_conversation_id(conversation_id),
    }


def _failure_plan(bridge, message, conversation_id):
    mode = "risk_based"
    risk = "low"
    allow_synthetic = False
    constrained_by = []
    try:
        policy = bridge._agent_policy_layers(
            _safe_conversation_id(conversation_id),
            _safe_message(message) or "No se pudo completar la petición.",
        )["layers"]
        user = policy.get("user", {})
        mode = user.get("confirmation_mode", mode)
        risk = user.get("max_auto_risk", risk)
        allow_synthetic = all(
            bool(value.get("allow_synthetic_data"))
            for value in policy.values()
            if isinstance(value, dict)
        )
        constrained_by = ["user"]
    except Exception:  # noqa: BLE001 - display policy is best-effort only
        pass
    if mode not in {"always_confirm", "risk_based", "protected_only"}:
        mode = "risk_based"
    if risk not in {"low", "moderate", "high", "protected"}:
        risk = "low"
    return {
        "plan_id": str(uuid4()),
        "state": "failed",
        "risk": "low",
        "metadata": {
            "needs_read": False,
            "needs_schema": False,
            "needs_write": False,
            "needs_business_action": False,
            "has_external_effect": False,
            "has_irreversible_effect": False,
            "is_atomic": True,
            "estimated_blast_radius": 0,
        },
        "policy": {
            "confirmation_mode": mode,
            "max_auto_risk": risk,
            "allow_synthetic_data": allow_synthetic,
            "constrained_by": constrained_by,
        },
        "goal": "Explicar por qué no se pudo completar la petición.",
        "assumptions": [],
        "steps": [],
        "requires_confirmation": False,
        "expires_at": None,
    }


def _failure_answer(code):
    normalized = str(code or "service_unavailable").casefold()
    if normalized in {"access_denied", "query_rejected", "action_rejected"}:
        diagnosis = "Odoo ha rechazado el acceso o la operación necesaria para completar la petición."
        reason = (
            "El asistente usa tu usuario real y respeta sus permisos, reglas de registro, campos "
            "accesibles y compañías activas."
        )
        solution = (
            "No doy la operación por completada. Si deberías tener acceso, revisa grupos, ACL, "
            "reglas de registro y compañías del usuario; si no, necesitarás que un administrador "
            "amplíe esos permisos."
        )
    elif "timeout" in normalized:
        diagnosis = "La petición no terminó dentro del tiempo seguro disponible."
        reason = (
            "El motor o una comprobación necesaria tardó más que el límite configurado y el turno "
            "se detuvo antes de validar un resultado final."
        )
        solution = (
            "No doy la operación por completada. Reintenta una vez; si ocurre de nuevo con una "
            "petición pequeña, revisa Diagnostics y los tiempos del Assistant/Codex."
        )
    elif any(marker in normalized for marker in ("budget", "limit", "repeated")):
        diagnosis = "El agente activó un límite de seguridad durante una cadena de comprobaciones."
        reason = (
            "Se agotó un presupuesto de herramientas o intentos antes de obtener un resultado "
            "suficientemente fiable."
        )
        solution = (
            "No doy la operación por completada. Reintenta una vez; si una petición sencilla vuelve "
            "a llegar a este límite, debe revisarse como un problema del runtime en Diagnostics."
        )
    elif normalized in {"engine_unavailable", "authentication_failed", "service_unavailable"}:
        diagnosis = "El Assistant no ha podido mantener disponible el motor necesario para este turno."
        reason = (
            "La conexión, autenticación o proceso del servicio se interrumpió antes de producir una "
            "respuesta verificable."
        )
        solution = (
            "No doy la operación por completada. Reintenta una vez; si persiste, revisa Diagnostics "
            "para comprobar Assistant Service, Codex y su autenticación."
        )
    elif normalized == "evidence_unavailable":
        diagnosis = "No he podido reunir evidencia suficiente para responder con fiabilidad."
        reason = "La fuente necesaria para verificar esa parte de la respuesta no estaba disponible."
        solution = (
            "No voy a sustituir esa evidencia por una suposición. Comprueba Source/Knowledge en "
            "Diagnostics y reindexa sólo si la fuente aparece desactualizada o sin indexar."
        )
    elif normalized in {"invalid_context", "record_context_required"}:
        diagnosis = "No he podido resolver de forma segura el contexto necesario para esta petición."
        reason = (
            "La petición no pudo vincularse con un objetivo válido sin hacer una suposición insegura."
        )
        solution = (
            "No necesitas abrir una pantalla concreta para darme acceso. Reintenta indicando el "
            "concepto o registro; si vuelve a pasar, debe revisarse la detección de modelos."
        )
    else:
        diagnosis = "No he podido completar esta petición de forma verificable."
        reason = "El turno se interrumpió antes de producir un resultado que pudiera validarse con seguridad."
        solution = (
            "No doy la operación por completada. Reintenta una vez; si vuelve a ocurrir, revisa "
            "Diagnostics para localizar el componente que está fallando."
        )
    return (
        f"**Diagnóstico.** {diagnosis}\n\n"
        f"**Motivo.** {reason}\n\n"
        f"**Solución.** {solution}"
    )


def _error_code(result):
    error = result.get("error") if isinstance(result, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) and code else "service_unavailable"


def _safe_message(value):
    if not isinstance(value, str):
        return ""
    normalized = value.strip()
    return normalized[:4000] if normalized and "\x00" not in normalized else ""


def _safe_conversation_id(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return str(parsed) if str(parsed) == value else None
