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

const PROFILE_ICONS = {
    strict: "fa-hand-paper-o",
    balanced: "fa-balance-scale",
    autonomous: "fa-bolt",
    full_access: "fa-unlock-alt",
};

patch(AssistantPanel.prototype, {
    get autonomyProfileLabel() {
        return PROFILE_LABELS[this.state.autonomyProfile] || PROFILE_LABELS.balanced;
    },

    get autonomyProfileIconClass() {
        return PROFILE_ICONS[this.state.autonomyProfile] || PROFILE_ICONS.balanced;
    },

    get recoveryPending() {
        return this.executionPending || this.recoveryReviewRequired;
    },

    get executionPending() {
        return ["authorized", "executing"].includes(this.state.result?.plan?.state);
    },

    get recoveryReviewRequired() {
        return (
            this.state.actionReceipt?.state === "recovery_required" ||
            typeof this.state.recoveryPlanId === "string"
        );
    },

    get recoveryExecuting() {
        return this.state.result?.plan?.state === "executing";
    },

    get actionDecisionMessage() {
        const messages = {
            authorized: _t(
                "La acción aprobada está en cola. Odoo conserva el mismo plan y no crea una autorización nueva."
            ),
            executing: _t(
                "La ejecución sigue en curso. El Assistant sólo comprobará su estado hasta que Odoo confirme un resultado o habilite una recuperación segura."
            ),
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
