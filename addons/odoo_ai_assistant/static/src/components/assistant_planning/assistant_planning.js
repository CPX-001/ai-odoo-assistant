/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

const MODE_LABELS = {
    adaptive: _t("Adaptativo"),
    deliberate: _t("Plan"),
    auto: _t("Auto"),
};

const MODE_ICONS = {
    adaptive: "fa-random",
    deliberate: "fa-list-ol",
    auto: "fa-magic",
};

patch(AssistantPanel.prototype, {
    get planningModeLabel() {
        return MODE_LABELS[this.state.planningMode] || MODE_LABELS.adaptive;
    },

    get planningModeIconClass() {
        return MODE_ICONS[this.state.planningMode] || MODE_ICONS.adaptive;
    },

    async selectPlanningMode(mode) {
        await this.panel.setPlanningMode(mode);
    },
});
