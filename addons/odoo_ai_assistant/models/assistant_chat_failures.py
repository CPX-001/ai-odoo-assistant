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
        code = _error_code(result)
        # A malformed/tampered provider payload remains rejected at the trusted bridge boundary.
        # The Owl presentation layer converts even this stable code into a conversational
        # fallback, so fail-closed validation is preserved without showing raw errors.
        if code == "invalid_response":
            return result
        failure = _failure_chat_result(
            self,
            code=code,
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
        except Exception:  # noqa: BLE001 - the fallback must survive history failures
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
        return (
            "No he podido continuar porque Odoo no me ha permitido acceder o realizar una parte "
            "necesaria de la petición. No he hecho ningún cambio. Si debería estar permitido, habrá "
            "que revisar los permisos de tu usuario."
        )
    if "timeout" in normalized:
        return (
            "La petición se ha quedado sin tiempo antes de terminar. No he dado nada por hecho ni "
            "por aplicado. Puedes reintentarlo; si se repite, habrá que revisar qué parte está "
            "tardando demasiado."
        )
    if any(marker in normalized for marker in ("budget", "limit", "repeated")):
        return (
            "He tenido que parar antes de terminar porque el proceso entró en demasiadas "
            "comprobaciones o intentos. No he dado la petición por completada. Puedes reintentarlo "
            "una vez; si vuelve a pasar, habrá que revisar por qué se atasca."
        )
    if normalized == "evidence_unavailable":
        return (
            "No he encontrado información suficiente para responder con fiabilidad y prefiero no "
            "inventarla. No he dado nada por completado."
        )
    if normalized in {"invalid_context", "record_context_required"}:
        return (
            "No he podido identificar con suficiente seguridad a qué datos o registro se refería la "
            "petición. No necesitas abrir una pantalla concreta para darme acceso; puedes "
            "reintentarlo indicando el concepto o registro con un poco más de precisión."
        )
    if normalized in {"engine_unavailable", "authentication_failed", "service_unavailable"}:
        return (
            "No he podido terminar esta petición porque el servicio que la procesa no respondió "
            "correctamente. No sé todavía por qué y no voy a inventarlo. No he hecho ningún cambio. "
            "Puedes reintentarlo; si se repite, habrá que revisar el estado interno del Assistant."
        )
    return (
        "No he podido completar la petición de forma fiable. No tengo suficiente información para "
        "afirmar la causa y no voy a inventarla. No he dado nada por completado."
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
