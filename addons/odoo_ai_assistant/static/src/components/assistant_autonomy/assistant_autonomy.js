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

    async selectAutonomyProfile(event) {
        const profile = event.currentTarget?.dataset?.profile;
        const details = event.currentTarget?.closest?.("details");
        details?.removeAttribute?.("open");
        await this.panel.setAutonomyProfile(profile);
    },
});
