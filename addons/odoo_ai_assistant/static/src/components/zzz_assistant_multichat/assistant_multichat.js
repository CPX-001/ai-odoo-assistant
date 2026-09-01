/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AssistantHistory } from "@odoo_ai_assistant/components/assistant_history/assistant_history";

patch(AssistantHistory.prototype, {
    get isNavigationBusy() {
        return this.ui.deleting || this.state.historyLoading;
    },

    newConversation() {
        if (!this.isNavigationBusy) {
            this.panel.newConversation();
        }
    },

    async onConversationClick(event) {
        const conversationId = event.currentTarget.dataset.conversationId;
        if (!conversationId) {
            return;
        }
        if (this.ui.selectionMode) {
            if (!this.isBusy) {
                this.toggleSelected(conversationId);
            }
            return;
        }
        if (this.isNavigationBusy) {
            return;
        }
        await this.panel.selectConversation(conversationId);
    },
});
