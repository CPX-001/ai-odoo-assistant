/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        panel.state.historyView = panel.state.conversationId === null;

        return {
            ...panel,
            open() {
                panel.open();
                if (!panel.state.conversationId) {
                    panel.state.historyView = true;
                }
            },
            showHistory() {
                panel.state.historyView = true;
            },
            newConversation() {
                panel.newConversation();
                panel.state.historyView = false;
            },
            async selectConversation(conversationId) {
                const loaded = await panel.selectConversation(conversationId);
                if (loaded) {
                    panel.state.historyView = false;
                }
                return loaded;
            },
        };
    },
});
