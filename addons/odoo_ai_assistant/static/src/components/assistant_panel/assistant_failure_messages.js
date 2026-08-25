/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

const FAILURE_DETAILS = {
    access_denied: {
        diagnosis: _t("Odoo ha rechazado el acceso necesario para completar la petición."),
        reason: _t(
            "El asistente trabaja con tu usuario real y respeta sus permisos, reglas de registro, campos accesibles y compañías activas."
        ),
        solution: _t(
            "Si deberías tener acceso, revisa los grupos, ACL, reglas de registro y compañías del usuario; si no, necesitarás que un administrador amplíe esos permisos."
        ),
    },
    agent_budget_exceeded: {
        diagnosis: _t("El agente activó un límite de seguridad durante una cadena de comprobaciones."),
        reason: _t(
            "Se agotó un presupuesto de herramientas o intentos antes de obtener un resultado suficientemente fiable."
        ),
        solution: _t(
            "Reintenta una vez. Si una petición sencilla vuelve a alcanzar el límite, debe revisarse como un problema del runtime en Diagnostics."
        ),
    },
    action_budget_exceeded: {
        diagnosis: _t("La preparación de la operación alcanzó un límite de seguridad."),
        reason: _t("No fue posible validar todos los pasos necesarios dentro del presupuesto del turno."),
        solution: _t(
            "No doy la operación por completada. Reintenta una vez y, si se repite, revisa Diagnostics antes de ampliar límites."
        ),
    },
    action_rejected: {
        diagnosis: _t("Odoo o la política del asistente ha rechazado la operación solicitada."),
        reason: _t(
            "La acción no cumplió las condiciones de seguridad, permisos o reglas de negocio necesarias para continuar."
        ),
        solution: _t(
            "No se considera completada. Revisa el estado del registro y tus permisos; si la operación debería ser válida, consulta Diagnostics."
        ),
    },
    authentication_failed: {
        diagnosis: _t("El Assistant no ha podido autenticarse correctamente con uno de sus componentes internos."),
        reason: _t("La sesión técnica necesaria para completar el turno no pudo validarse."),
        solution: _t(
            "Reintenta una vez. Si persiste, revisa la configuración y el estado de autenticación en Diagnostics."
        ),
    },
    engine_timeout: {
        diagnosis: _t("La petición no terminó dentro del tiempo seguro disponible."),
        reason: _t(
            "El motor de razonamiento o una comprobación necesaria tardó más que el límite configurado."
        ),
        solution: _t(
            "No doy la operación por completada. Reintenta una vez; si ocurre de nuevo con una petición pequeña, revisa los tiempos del Assistant en Diagnostics."
        ),
    },
    engine_unavailable: {
        diagnosis: _t("El motor de razonamiento no estaba disponible para terminar este turno."),
        reason: _t(
            "El Assistant no pudo iniciar o mantener una sesión válida hasta producir una respuesta verificable."
        ),
        solution: _t(
            "No doy la operación por completada. Reintenta una vez; si persiste, comprueba el estado del motor y su autenticación en Diagnostics."
        ),
    },
    evidence_unavailable: {
        diagnosis: _t("No he podido reunir evidencia suficiente para responder con fiabilidad."),
        reason: _t("La fuente necesaria para verificar esa parte de la respuesta no estaba disponible."),
        solution: _t(
            "No voy a sustituir esa evidencia por una suposición. Comprueba Source/Knowledge en Diagnostics y reindexa sólo si la fuente aparece desactualizada o sin indexar."
        ),
    },
    invalid_context: {
        diagnosis: _t("No he podido resolver de forma segura el contexto necesario para esta petición."),
        reason: _t(
            "La petición no pudo vincularse con un objetivo válido sin hacer una suposición insegura."
        ),
        solution: _t(
            "No necesitas abrir una pantalla concreta para darme acceso. Reintenta indicando el concepto o registro; si vuelve a pasar, debe revisarse la detección de modelos."
        ),
    },
    invalid_response: {
        diagnosis: _t("La respuesta recibida no superó las validaciones de seguridad del Assistant."),
        reason: _t(
            "El contenido o la estructura devuelta no coincidió con el contrato esperado, por lo que no es seguro presentarla como válida."
        ),
        solution: _t(
            "No doy la operación por completada. Reintenta una vez; si se repite, revisa Diagnostics porque puede existir una incompatibilidad o regresión del runtime."
        ),
    },
    query_budget_exceeded: {
        diagnosis: _t("La consulta alcanzó un límite de seguridad antes de terminar."),
        reason: _t("No fue posible completar todas las comprobaciones necesarias dentro del presupuesto del turno."),
        solution: _t(
            "Reintenta una vez. Si la consulta es pequeña y vuelve a ocurrir, revisa Diagnostics porque no debería ser un límite normal de uso."
        ),
    },
    query_rejected: {
        diagnosis: _t("Odoo ha rechazado la consulta solicitada."),
        reason: _t(
            "El modelo, campo o filtro no estaba permitido por el esquema efectivo y los permisos del usuario."
        ),
        solution: _t(
            "Reformula la consulta si pedía un campo no accesible. Si debería estar permitido, revisa permisos y Diagnostics."
        ),
    },
    record_context_required: {
        diagnosis: _t("La operación no pudo resolver un registro objetivo de forma segura."),
        reason: _t("Falta un objetivo material que el host pueda validar sin adivinarlo."),
        solution: _t(
            "Indica el registro o criterio que quieres usar. No necesitas navegar a una vista concreta únicamente para conceder acceso."
        ),
    },
    service_unavailable: {
        diagnosis: _t("El Assistant Service no estaba disponible para terminar este turno."),
        reason: _t("La comunicación con el servicio se interrumpió antes de obtener una respuesta verificable."),
        solution: _t(
            "No doy la operación por completada. Reintenta una vez; si persiste, comprueba el estado del servicio y la conectividad en Diagnostics."
        ),
    },
};

const GENERIC_FAILURE = {
    diagnosis: _t("No he podido completar esta petición de forma verificable."),
    reason: _t("El turno se interrumpió antes de producir un resultado que pudiera validarse con seguridad."),
    solution: _t(
        "No doy la operación por completada. Reintenta una vez; si vuelve a ocurrir, revisa Diagnostics para localizar el componente que está fallando."
    ),
};

export function failureMessage(code) {
    const detail = FAILURE_DETAILS[code] || GENERIC_FAILURE;
    return `${_t("Diagnóstico:")} ${detail.diagnosis}\n\n${_t("Motivo:")} ${detail.reason}\n\n${_t("Solución:")} ${detail.solution}`;
}

patch(AssistantPanel.prototype, {
    get errorMessage() {
        return failureMessage(this.state.errorCode);
    },
});
