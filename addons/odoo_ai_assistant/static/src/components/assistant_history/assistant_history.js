/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

const HISTORY_SEARCH_THRESHOLD = 8;
const HISTORY_DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
});

export class AssistantHistory extends Component {
    static template = "odoo_ai_assistant.AssistantHistory";
    static props = {};

    setup() {
        this.panel = useService("odoo_ai_assistant_panel");
        this.state = useState(this.panel.state);
        this.ui = useState({ search: "" });
    }

    get showSearch() {
        return this.state.conversations.length > HISTORY_SEARCH_THRESHOLD;
    }

    get conversations() {
        const query = this.ui.search.trim().toLocaleLowerCase();
        if (!query) {
            return this.state.conversations;
        }
        return this.state.conversations.filter((conversation) =>
            conversation.title.toLocaleLowerCase().includes(query)
        );
    }

    get isBusy() {
        return (
            this.state.loading ||
            this.state.historyLoading ||
            this.state.decisionLoading ||
            this.state.result?.plan?.state === "authorized"
        );
    }

    newConversation() {
        if (!this.isBusy) {
            this.panel.newConversation();
        }
    }

    async selectConversation(event) {
        const conversationId = event.currentTarget.dataset.conversationId;
        if (!this.isBusy && conversationId) {
            await this.panel.selectConversation(conversationId);
        }
    }

    onSearchInput(event) {
        this.ui.search = String(event.target.value || "").slice(0, 160);
    }

    formatUpdatedAt(value) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return "";
        }
        const elapsedSeconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
        if (elapsedSeconds < 60) {
            return "ahora";
        }
        const minutes = Math.floor(elapsedSeconds / 60);
        if (minutes < 60) {
            return `hace ${minutes} min`;
        }
        const hours = Math.floor(minutes / 60);
        if (hours < 24) {
            return `hace ${hours} h`;
        }
        const days = Math.floor(hours / 24);
        if (days < 7) {
            return `hace ${days} d`;
        }
        return HISTORY_DATE_FORMAT.format(date);
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
