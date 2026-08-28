/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import { failureCanRetry, failureRequiresReview } from "@odoo_ai_assistant/services/assistant_failure_contract";
const LEGACY_MESSAGES = {
    access_denied: () => _t("Odoo no ha permitido acceder a los datos necesarios. Revisa los permisos del usuario antes de continuar."),
    authentication_failed: () => _t("La conexión con ChatGPT necesita volver a autenticarse antes de continuar."),
    codex_not_connected: () => _t("Conecta una cuenta de ChatGPT para usar el Assistant."),
    codex_unavailable: () => _t("Codex no está disponible para el proceso Odoo."),
    engine_timeout: () => _t("La petición agotó el tiempo disponible. Comprueba el estado actual antes de repetir una operación que pudiera modificar datos."),
    invalid_context: () => _t("No he podido identificar con suficiente seguridad el contexto necesario. Puedes precisar el registro o criterio que quieres usar."),
    invalid_response: () => _t("El Assistant recibió una respuesta que no pudo validar con seguridad."),
    worker_lost_after_write_barrier: () => _t("La ejecución quedó sin un resultado concluyente después de iniciar una operación. Revisa el estado actual y no repitas la acción a ciegas."),
};
const CATEGORY_BODY = {
    authentication: () => _t("ChatGPT rechazó o perdió la autenticación necesaria para este turno."), odoo_access: () => _t("Odoo ha denegado el acceso requerido con los permisos efectivos de tu usuario."),
    provider_connection: () => _t("Se interrumpió la comunicación con el proveedor de razonamiento."), provider_protocol: () => _t("La respuesta del proveedor no cumplió el protocolo esperado por el host."),
    provider_capacity: () => _t("El proveedor de razonamiento no pudo atender la petición por capacidad o límites temporales."), provider_output: () => _t("La salida del proveedor no pudo validarse de forma segura."),
    capability_discovery: () => _t("La capacidad necesaria no estaba disponible en el catálogo efectivo del turno."), capability_input: () => _t("La herramienta recibió argumentos que no cumplen su contrato validado."),
    capability_execution: () => _t("Una herramienta no pudo completar la operación solicitada."), capability_output: () => _t("El resultado de una herramienta no cumplió su contrato de salida."),
    policy: () => _t("La política del host no autoriza continuar con esa operación."), approval: () => _t("La operación no puede continuar con el estado actual de aprobación."), retrieval: () => _t("No fue posible obtener la evidencia necesaria de forma fiable."),
    verification: () => _t("No fue posible verificar de forma concluyente el resultado de la operación."), write_execution: () => _t("La ejecución de la operación no terminó de forma concluyente."), queue_worker: () => _t("El worker que procesaba el turno no pudo finalizarlo de forma normal."),
    persistence: () => _t("Odoo no pudo persistir correctamente el estado final del turno."), cancellation: () => _t("El turno fue cancelado antes de completarse."), input: () => _t("La petición no cumple los límites de entrada del Assistant."),
    context: () => _t("El contexto disponible no es suficiente o no es válido para continuar."), internal: () => _t("El turno terminó con un fallo interno acotado por el host."),
};
function effectNotice(failure) {
    if (!failure) return ""; if (["none", "not_started"].includes(failure.effect_state)) return _t("No se ha iniciado ningún cambio de negocio en este turno.");
    if (failure.effect_state === "confirmed") return _t("El efecto de negocio registrado por el host quedó confirmado.");
    if (failure.effect_state === "partial") return _t("La operación pudo completarse sólo en parte. Revisa el resultado antes de continuar.");
    return _t("No se puede confirmar si la operación llegó a producir efectos. Revisa el estado actual y no repitas la acción a ciegas.");
}
function nextStep(failure) {
    if (!failure) return ""; if (failureRequiresReview(failure)) return _t("Comprueba los datos afectados o el estado del plan antes de realizar otra acción.");
    const actions = { retry: failureCanRetry(failure) ? _t("Puedes reintentar esta petición de forma segura.") : _t("No se ofrece un reintento automático para este fallo."), reconnect: _t("Vuelve a conectar ChatGPT y envía de nuevo la petición cuando la conexión esté disponible."), clarify: _t("Aclara el registro, criterio o dato necesario y vuelve a intentarlo."), request_access: _t("Solicita o revisa los permisos necesarios en Odoo antes de volver a intentarlo."), review: _t("Revisa el estado actual antes de decidir el siguiente paso."), none: "" }; return actions[failure.user_action] || "";
}
export function failurePresentation(failure, compatibilityCode = null) {
    if (!failure) return { body: (LEGACY_MESSAGES[compatibilityCode] || (() => _t("No he podido completar la petición de forma fiable. El código técnico se conserva para diagnóstico sin inventar una causa.")))(), effect: "", next: "", technical: compatibilityCode ? _t("Código: %s", compatibilityCode) : "", canRetry: false };
    return { body: (CATEGORY_BODY[failure.category] || CATEGORY_BODY.internal)(), effect: effectNotice(failure), next: nextStep(failure), technical: _t("Código: %s · Diagnóstico: %s", failure.code, failure.diagnostic_id), canRetry: failureCanRetry(failure) };
}
export function failureMessage(code, failure = null) { const view = failurePresentation(failure, code); return [view.body, view.effect, view.next].filter(Boolean).join(" "); }
patch(AssistantPanel.prototype, {
    get failureView() { return failurePresentation(this.state.failure, this.state.errorCode); }, get errorMessage() { return this.failureView.body; }, get failureEffectNotice() { return this.failureView.effect; }, get failureNextStep() { return this.failureView.next; }, get failureTechnical() { return this.failureView.technical; }, get failureCanRetry() { return this.failureView.canRetry; }, retryFailure() { return this.panel.retryFailure?.(); },
});
