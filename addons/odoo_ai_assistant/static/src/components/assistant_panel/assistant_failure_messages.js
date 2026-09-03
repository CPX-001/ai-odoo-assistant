/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import {
    failureCanRetry,
    failureRequiresReview,
} from "@odoo_ai_assistant/services/assistant_failure_contract";

const LEGACY_MESSAGES = {
    access_denied: () =>
        _t(
            "No he podido continuar porque Odoo no me ha permitido acceder a algo que necesitaba. No doy ningún cambio por realizado. Si ese acceso debería estar permitido, habrá que revisar los permisos de tu usuario."
        ),
    authentication_failed: () =>
        _t(
            "No he podido terminar esta petición porque una parte necesaria del Assistant no estaba disponible correctamente. No tengo suficiente información para darte una causa fiable y no doy ningún cambio por confirmado."
        ),
    codex_not_connected: () => _t("Conecta una cuenta de ChatGPT para usar el Assistant."),
    codex_unavailable: () => _t("Codex no está disponible para el proceso Odoo."),
    engine_timeout: () =>
        _t(
            "La petición se ha quedado sin tiempo antes de terminar. No doy ningún resultado ni cambio por confirmado. Si era una consulta puedes reintentarlo; si pedías modificar datos, comprueba primero su estado actual antes de repetir la operación."
        ),
    service_unavailable: () =>
        _t(
            "Se ha interrumpido la comunicación antes de que pudiera confirmar el resultado. Si pedías cambiar datos, no puedo asegurar si el cambio llegó a aplicarse: comprueba su estado actual antes de repetir la operación."
        ),
    invalid_context: () =>
        _t(
            "No he podido identificar con suficiente seguridad a qué datos o registro se refería la petición. No necesitas abrir una pantalla concreta para darme acceso; puedes indicarme el concepto o registro con un poco más de precisión."
        ),
    record_context_required: () =>
        _t(
            "No he podido identificar con suficiente seguridad el registro necesario. No necesitas abrir una pantalla concreta para darme acceso; puedes indicarme el registro o el criterio que quieres usar."
        ),
    invalid_response: () =>
        _t(
            "He recibido una respuesta que no he podido validar con seguridad. Si pedías modificar datos, no puedo asegurar el resultado: comprueba su estado actual antes de repetir la operación."
        ),
    worker_lost_after_write_barrier: () =>
        _t(
            "La ejecución quedó sin un resultado concluyente después de iniciar una operación. Revisa el estado actual y no repitas la acción a ciegas."
        ),
};

const CATEGORY_BODY = {
    authentication: () => _t("ChatGPT rechazó o perdió la autenticación necesaria para este turno."),
    odoo_access: () =>
        _t("Odoo ha denegado el acceso requerido con los permisos efectivos de tu usuario."),
    provider_connection: () => _t("Se interrumpió la comunicación con el proveedor de razonamiento."),
    provider_protocol: () =>
        _t("La respuesta del proveedor no cumplió el protocolo esperado por el host."),
    provider_capacity: () =>
        _t("El proveedor de razonamiento no pudo atender la petición por capacidad o límites temporales."),
    provider_output: () => _t("La salida del proveedor no pudo validarse de forma segura."),
    capability_discovery: () =>
        _t("La capacidad necesaria no estaba disponible en el catálogo efectivo del turno."),
    capability_input: () => _t("La herramienta recibió argumentos que no cumplen su contrato validado."),
    capability_execution: () => _t("Una herramienta no pudo completar la operación solicitada."),
    capability_output: () => _t("El resultado de una herramienta no cumplió su contrato de salida."),
    policy: () => _t("La política del host no autoriza continuar con esa operación."),
    approval: () => _t("La operación no puede continuar con el estado actual de aprobación."),
    retrieval: () => _t("No fue posible obtener la evidencia necesaria de forma fiable."),
    verification: () => _t("No fue posible verificar de forma concluyente el resultado de la operación."),
    write_execution: () => _t("La ejecución de la operación no terminó de forma concluyente."),
    queue_worker: () => _t("El worker que procesaba el turno no pudo finalizarlo de forma normal."),
    persistence: () => _t("Odoo no pudo persistir correctamente el estado final del turno."),
    cancellation: () => _t("El turno fue cancelado antes de completarse."),
    input: () => _t("La petición no cumple los límites de entrada del Assistant."),
    context: () => _t("El contexto disponible no es suficiente o no es válido para continuar."),
    internal: () => _t("El turno terminó con un fallo interno acotado por el host."),
};

function effectNotice(failure) {
    if (!failure) {
        return "";
    }
    if (["none", "not_started"].includes(failure.effect_state)) {
        return _t("No se ha iniciado ningún cambio de negocio en este turno.");
    }
    if (failure.effect_state === "confirmed") {
        return _t("El efecto de negocio registrado por el host quedó confirmado.");
    }
    if (failure.effect_state === "partial") {
        return _t("La operación pudo completarse sólo en parte. Revisa el resultado antes de continuar.");
    }
    return _t(
        "No se puede confirmar si la operación llegó a producir efectos. Revisa el estado actual y no repitas la acción a ciegas."
    );
}

function nextStep(failure) {
    if (!failure) {
        return "";
    }
    if (failureRequiresReview(failure)) {
        return _t("Comprueba los datos afectados o el estado de la operación antes de realizar otra acción.");
    }
    if (failure.provider_code === "usageLimitExceeded") {
        return _t(
            "Revisa los límites de la cuenta de ChatGPT conectada o conecta una cuenta con capacidad disponible antes de volver a intentarlo."
        );
    }
    const actions = {
        retry: failureCanRetry(failure)
            ? _t("Puedes reintentar esta petición de forma segura.")
            : _t("No se ofrece un reintento automático para este fallo."),
        reconnect: _t("Vuelve a conectar ChatGPT y envía de nuevo la petición cuando la conexión esté disponible."),
        clarify: _t("Aclara el registro, criterio o dato necesario y vuelve a intentarlo."),
        request_access: _t("Solicita o revisa los permisos necesarios en Odoo antes de volver a intentarlo."),
        review: _t("Revisa el estado actual antes de decidir el siguiente paso."),
        none: "",
    };
    return actions[failure.user_action] || "";
}

export function failurePresentation(failure, compatibilityCode = null) {
    if (!failure) {
        const fallback = () =>
            _t(
                "No he podido completar la petición de forma fiable. No tengo suficiente información para afirmar la causa y no voy a inventarla. No doy ningún cambio por confirmado."
            );
        return {
            body: (LEGACY_MESSAGES[compatibilityCode] || fallback)(),
            effect: "",
            next: "",
            technical: compatibilityCode ? _t("Código: %s", compatibilityCode) : "",
            canRetry: false,
        };
    }
    const body =
        failure.provider_code === "usageLimitExceeded"
            ? _t("La cuenta de ChatGPT conectada ha alcanzado su límite de uso.")
            : (CATEGORY_BODY[failure.category] || CATEGORY_BODY.internal)();
    return {
        body,
        effect: effectNotice(failure),
        next: nextStep(failure),
        technical: _t("Código: %s · Diagnóstico: %s", failure.code, failure.diagnostic_id),
        canRetry: failureCanRetry(failure),
    };
}

export function failureMessage(code, failure = null) {
    const view = failurePresentation(failure, code);
    return [view.body, view.effect, view.next].filter(Boolean).join(" ");
}

patch(AssistantPanel.prototype, {
    get failureView() {
        return failurePresentation(this.state.failure, this.state.errorCode);
    },
    get errorMessage() {
        return this.failureView.body;
    },
    get failureEffectNotice() {
        return this.failureView.effect;
    },
    get failureNextStep() {
        return this.failureView.next;
    },
    get failureTechnical() {
        return this.failureView.technical;
    },
    get failureCanRetry() {
        return this.failureView.canRetry;
    },
    retryFailure() {
        return this.panel.retryFailure?.();
    },
});
