/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

function firstPlanErrorCode(plan) {
    for (const step of plan?.steps || []) {
        const code = step?.receipt?.error_code;
        if (typeof code === "string" && code) {
            return code;
        }
    }
    return null;
}

export function failedActionMessage(plan) {
    const code = firstPlanErrorCode(plan);
    if (code === "access_denied") {
        return _t(
            "Odoo no me ha permitido aplicar este cambio con tus permisos actuales, así que no lo doy por completado. Si esperabas poder hacerlo, habrá que revisar los permisos de tu usuario."
        );
    }
    if (["business_rule_rejected", "invalid_action_state"].includes(code)) {
        return _t(
            "Odoo ha rechazado el cambio porque el estado actual del registro o una regla de negocio no permite hacerlo así. No lo doy por completado. Puedo revisar el registro y decirte qué condición o paso previo lo está bloqueando."
        );
    }
    if (code === "stale_precondition") {
        return _t(
            "El registro cambió después de preparar la operación y he evitado aplicar una versión ya desactualizada. Puedo volver a leer su estado actual y preparar el cambio de nuevo."
        );
    }
    if (["verification_mismatch", "verification_unavailable"].includes(code)) {
        return _t(
            "No he podido verificar con seguridad cómo terminó la operación, así que no la doy por completada. Conviene comprobar el estado actual del registro antes de repetirla; puedo hacerlo en una nueva petición."
        );
    }
    return _t(
        "Odoo no ha podido completar la operación de forma verificable. No voy a inventar una causa que no tengo confirmada. Comprueba el estado actual antes de repetir el cambio; si quieres, puedo revisarlo en una nueva petición."
    );
}

patch(AssistantPanel.prototype, {
    get actionDecisionMessage() {
        const state = this.state.actionReceipt?.state;
        if (state === "failed") {
            return failedActionMessage(this.state.result?.plan);
        }
        const messages = {
            authorized: _t(
                "El resultado del lote quedó pendiente de recuperar. Se conserva el mismo intento y no se crea una nueva autorización."
            ),
            completed: _t("Operación completada y verificada en Odoo."),
            rejected: _t("Operación cancelada."),
            partial: _t(
                "La operación terminó parcialmente. Revisa el resultado antes de continuar."
            ),
        };
        return messages[state] || "";
    },
});
