/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

const PROFILE_LABELS = {
    strict: _t("Estricto"),
    balanced: _t("Equilibrado"),
    autonomous: _t("Autónomo"),
    full_access: _t("Acceso completo"),
};

patch(AssistantPanel.prototype, {
    get autonomyProfileLabel() {
        return PROFILE_LABELS[this.state.autonomyProfile] || PROFILE_LABELS.balanced;
    },

    get actionDecisionMessage() {
        const messages = {
            completed: _t("Acción completada y verificada en Odoo."),
            rejected: _t("Acción cancelada. No se realizó ningún cambio."),
            partial: _t("La operación se completó parcialmente; revisa el resultado."),
            failed: _t("La operación no pudo completarse."),
        };
        return messages[this.state.actionReceipt?.state] || "";
    },

    async selectAutonomyProfile(profile) {
        await this.panel.setAutonomyProfile(profile);
    },
});
