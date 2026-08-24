/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

const HISTORY_DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
});

export class AssistantHistory extends Component {
    static template = "odoo_ai_assistant.AssistantHistory";
    static props = {};

    setup() {
        this.panel = useService("odoo_ai_assistant_panel");
        this.state = useState(this.panel.state);
    }

    get conversations() {
        return this.state.conversations;
    }

    get isBusy() {
        return this.state.loading || this.state.historyLoading || this.state.decisionLoading;
    }

    newConversation() {
        if (!this.isBusy) {
            this.panel.newConversation();
        }
    }

    async selectConversation(conversationId) {
        if (!this.isBusy) {
            await this.panel.selectConversation(conversationId);
        }
    }

    formatUpdatedAt(value) {
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? "" : HISTORY_DATE_FORMAT.format(date);
    }
}

patch(AssistantPanel, {
    components: {
        ...(AssistantPanel.components || {}),
        AssistantHistory,
    },
});

patch(AssistantPanel.prototype, {
    showHistory() {
        this.panel.showHistory();
    },
});
