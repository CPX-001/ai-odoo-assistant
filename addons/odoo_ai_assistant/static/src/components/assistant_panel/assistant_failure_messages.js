/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

const FAILURE_MESSAGES = {
    access_denied: () => _t(
        "No he podido continuar porque Odoo no me ha permitido acceder a algo que necesitaba. No doy ningún cambio por realizado. Si ese acceso debería estar permitido, habrá que revisar los permisos de tu usuario."
    ),
    engine_timeout: () => _t(
        "La petición se ha quedado sin tiempo antes de terminar. No doy ningún resultado ni cambio por confirmado. Si era una consulta puedes reintentarlo; si pedías modificar datos, comprueba primero su estado actual antes de repetir la operación."
    ),
    engine_unavailable: () => _t(
        "No he podido terminar esta petición porque una parte necesaria del Assistant no estaba disponible. No tengo una causa más concreta que pueda afirmar sin inventarla y no doy ningún cambio por confirmado."
    ),
    service_unavailable: () => _t(
        "Se ha interrumpido la comunicación antes de que pudiera confirmar el resultado. Si pedías cambiar datos, no puedo asegurar si el cambio llegó a aplicarse: comprueba su estado actual antes de repetir la operación."
    ),
    authentication_failed: () => _t(
        "No he podido terminar esta petición porque una parte necesaria del Assistant no estaba disponible correctamente. No tengo suficiente información para darte una causa fiable y no doy ningún cambio por confirmado."
    ),
    evidence_unavailable: () => _t(
        "No he encontrado información suficiente para responder con fiabilidad y prefiero no inventarla. No doy la petición por completada."
    ),
    invalid_context: () => _t(
        "No he podido identificar con suficiente seguridad a qué datos o registro se refería la petición. No necesitas abrir una pantalla concreta para darme acceso; puedes indicarme el concepto o registro con un poco más de precisión."
    ),
    record_context_required: () => _t(
        "No he podido identificar con suficiente seguridad el registro necesario. No necesitas abrir una pantalla concreta para darme acceso; puedes indicarme el registro o el criterio que quieres usar."
    ),
    invalid_response: () => _t(
        "He recibido una respuesta que no he podido validar con seguridad. Si pedías modificar datos, no puedo asegurar el resultado: comprueba su estado actual antes de repetir la operación."
    ),
};

const genericFailure = () =>
    _t(
        "No he podido completar la petición de forma fiable. No tengo suficiente información para afirmar la causa y no voy a inventarla. No doy ningún cambio por confirmado."
    );

export function failureMessage(code) {
    return (FAILURE_MESSAGES[code] || genericFailure)();
}

patch(AssistantPanel.prototype, {
    get errorMessage() {
        return failureMessage(this.state.errorCode);
    },
});
