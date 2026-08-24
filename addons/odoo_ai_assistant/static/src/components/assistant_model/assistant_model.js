/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

patch(AssistantPanel.prototype, {
    async selectReasoningModel(event) {
        await this.panel.setReasoningModel(event.target.value || null);
    },

    async openAssistantSettings() {
        this.panel.close();
        await this.actionService.doAction("base.action_res_config_settings", {
            additionalContext: { module: "odoo_ai_assistant" },
        });
    },
});
