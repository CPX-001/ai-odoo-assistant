/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

const FAILURE_MESSAGES = {
    access_denied: _t(
        "No he podido continuar porque Odoo no me ha permitido acceder a algo que necesitaba. No he hecho ningún cambio. Si ese acceso debería estar permitido, habrá que revisar los permisos de tu usuario."
    ),
    engine_timeout: _t(
        "La petición se ha quedado sin tiempo antes de terminar. No he dado nada por hecho ni por aplicado. Puedes reintentarlo; si vuelve a pasar, habrá que revisar qué parte está tardando demasiado."
    ),
    engine_unavailable: _t(
        "No he podido terminar esta petición porque el servicio que la procesa no respondió correctamente. No sé todavía por qué y no voy a inventarlo. No he hecho ningún cambio. Puedes reintentarlo."
    ),
    service_unavailable: _t(
        "No he podido terminar esta petición porque el servicio que la procesa no respondió correctamente. No sé todavía por qué y no voy a inventarlo. No he hecho ningún cambio. Puedes reintentarlo."
    ),
    authentication_failed: _t(
        "No he podido terminar esta petición porque una parte interna del Assistant no estaba disponible correctamente. No tengo suficiente información para darte una causa fiable. No he hecho ningún cambio."
    ),
    evidence_unavailable: _t(
        "No he encontrado información suficiente para responder con fiabilidad y prefiero no inventarla. No he dado nada por completado."
    ),
    invalid_context: _t(
        "No he podido identificar con suficiente seguridad a qué datos o registro se refería la petición. No necesitas abrir una pantalla concreta para darme acceso; puedes indicarme el concepto o registro con un poco más de precisión."
    ),
    record_context_required: _t(
        "No he podido identificar con suficiente seguridad el registro necesario. No necesitas abrir una pantalla concreta para darme acceso; puedes indicarme el registro o el criterio que quieres usar."
    ),
    invalid_response: _t(
        "He recibido una respuesta que no he podido validar con seguridad, así que no voy a presentarla como correcta. No he dado nada por completado. Puedes reintentarlo."
    ),
};

const GENERIC_FAILURE = _t(
    "No he podido completar la petición de forma fiable. No tengo suficiente información para afirmar la causa y no voy a inventarla. No he dado nada por completado."
);

export function failureMessage(code) {
    return FAILURE_MESSAGES[code] || GENERIC_FAILURE;
}

patch(AssistantPanel.prototype, {
    get errorMessage() {
        return failureMessage(this.state.errorCode);
    },
});
