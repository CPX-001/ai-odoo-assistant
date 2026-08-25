/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { CheckBox } from "@web/core/checkbox/checkbox";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import { historyActionsForScope } from "@odoo_ai_assistant/components/assistant_history/assistant_history_actions";

const HISTORY_SEARCH_THRESHOLD = 8;
const HISTORY_DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
});

export function toggleHistorySelection(selectedIds, conversationId) {
    const next = new Set(selectedIds);
    if (next.has(conversationId)) {
        next.delete(conversationId);
    } else {
        next.add(conversationId);
    }
    return [...next];
}

export function toggleVisibleHistorySelection(selectedIds, visibleIds) {
    const next = new Set(selectedIds);
    const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => next.has(id));
    for (const id of visibleIds) {
        if (allVisibleSelected) {
            next.delete(id);
        } else {
            next.add(id);
        }
    }
    return [...next];
}

export class AssistantHistory extends Component {
    static template = "odoo_ai_assistant.AssistantHistory";
    static components = { CheckBox, Dropdown, DropdownItem };
    static props = {};

    setup() {
        this.panel = useService("odoo_ai_assistant_panel");
        this.state = useState(this.panel.state);
        this.ui = useState({
            search: "",
            selectionMode: false,
            selectedIds: [],
            deleting: false,
        });
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

    get visibleConversationIds() {
        return this.conversations.map((conversation) => conversation.conversation_id);
    }

    get selectedCount() {
        return this.ui.selectedIds.length;
    }

    get allVisibleSelected() {
        const selected = new Set(this.ui.selectedIds);
        return (
            this.visibleConversationIds.length > 0 &&
            this.visibleConversationIds.every((conversationId) => selected.has(conversationId))
        );
    }

    get itemActions() {
        return historyActionsForScope("item");
    }

    get bulkActions() {
        return historyActionsForScope("bulk");
    }

    get isBusy() {
        return (
            this.ui.deleting ||
            this.state.loading ||
            this.state.historyLoading ||
            this.state.decisionLoading ||
            this.state.result?.plan?.state === "authorized"
        );
    }

    isSelected(conversationId) {
        return this.ui.selectedIds.includes(conversationId);
    }

    newConversation() {
        if (!this.isBusy) {
            this.panel.newConversation();
        }
    }

    async onConversationClick(event) {
        const conversationId = event.currentTarget.dataset.conversationId;
        if (this.isBusy || !conversationId) {
            return;
        }
        if (this.ui.selectionMode) {
            this.toggleSelected(conversationId);
            return;
        }
        await this.panel.selectConversation(conversationId);
    }

    enterSelection(conversationId = null) {
        if (this.isBusy) {
            return;
        }
        this.ui.selectionMode = true;
        this.ui.selectedIds = conversationId ? [conversationId] : [];
    }

    exitSelection() {
        this.ui.selectionMode = false;
        this.ui.selectedIds = [];
    }

    toggleSelected(conversationId) {
        if (!this.ui.selectionMode || this.isBusy || !conversationId) {
            return;
        }
        this.ui.selectedIds = toggleHistorySelection(this.ui.selectedIds, conversationId);
    }

    toggleAll() {
        if (!this.ui.selectionMode || this.isBusy) {
            return;
        }
        this.ui.selectedIds = toggleVisibleHistorySelection(
            this.ui.selectedIds,
            this.visibleConversationIds
        );
    }

    async runItemAction(action, conversationId) {
        if (this.isBusy || !action?.run || !conversationId) {
            return;
        }
        await action.run({ component: this, conversationIds: [conversationId] });
    }

    async runBulkAction(action) {
        if (this.isBusy || !action?.run || !this.selectedCount) {
            return;
        }
        await action.run({ component: this, conversationIds: [...this.ui.selectedIds] });
    }

    async deleteConversations(conversationIds) {
        const uniqueIds = [...new Set(conversationIds)].filter(Boolean);
        if (this.isBusy || !uniqueIds.length || uniqueIds.length > 50) {
            return false;
        }
        this.ui.deleting = true;
        this.state.errorCode = null;
        try {
            const response = await rpc("/odoo_ai/v1/chat-delete", {
                conversation_ids: uniqueIds,
            });
            if (response?.ok !== true || response.deleted_count !== uniqueIds.length) {
                this.state.errorCode = response?.error?.code || "invalid_response";
                return false;
            }
            this.exitSelection();
            await this.panel.loadHistory(null);
            return true;
        } catch {
            this.state.errorCode = "service_unavailable";
            return false;
        } finally {
            this.ui.deleting = false;
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
