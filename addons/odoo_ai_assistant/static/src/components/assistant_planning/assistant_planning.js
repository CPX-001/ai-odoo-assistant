/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

export function planningToggleTarget(mode) {
    return mode === "deliberate" ? "adaptive" : "deliberate";
}

patch(AssistantPanel.prototype, {
    get planModeActive() {
        return this.state.planningMode === "deliberate";
    },

    async togglePlanMode() {
        await this.panel.setPlanningMode(planningToggleTarget(this.state.planningMode));
    },
});
