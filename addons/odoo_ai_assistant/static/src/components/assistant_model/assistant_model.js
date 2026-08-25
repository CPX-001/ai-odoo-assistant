/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import { compactModelLabel } from "@odoo_ai_assistant/services/assistant_model_service";

patch(AssistantPanel.prototype, {
    get reasoningModelLabel() {
        const selected = this.state.modelOptions.find(
            (item) => item.model === this.state.selectedReasoningModel
        );
        return selected?.display_name || this.state.defaultReasoningModel || "Predeterminado";
    },

    get reasoningModelCompactLabel() {
        return compactModelLabel(this.reasoningModelLabel);
    },

    async selectReasoningModel(model) {
        await this.panel.setReasoningModel(model || null);
    },

    async openAssistantSettings() {
        this.panel.close();
        await this.actionService.doAction("base.action_res_config_settings", {
            additionalContext: { module: "odoo_ai_assistant" },
        });
    },
});
