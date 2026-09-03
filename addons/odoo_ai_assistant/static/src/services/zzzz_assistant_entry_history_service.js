/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";
import { clearRecentActiveChat } from "@odoo_ai_assistant/services/assistant_history_service";
import { createConversationTurnScope } from "@odoo_ai_assistant/services/zzz_assistant_turn_scope_service";

function browserSessionStorage() {
    try {
        return globalThis.sessionStorage || null;
    } catch {
        return null;
    }
}

/**
 * A browser/page bootstrap is not permission to reopen the last idle conversation.
 *
 * The live service instance still keeps the currently selected conversation when the panel is
 * merely closed and reopened. Only a newly composed Assistant service starts from history.
 */
export function prepareFreshAssistantEntry(
    state,
    { sessionStorage = browserSessionStorage() } = {}
) {
    clearRecentActiveChat(sessionStorage);

    // Reset only volatile presentation state. Stored per-conversation drafts and recovery handles
    // remain untouched; a user can reopen that conversation from history without losing anything.
    state.conversationId = null;
    state.activeTurn = null;
    state.messages = [];
    state.draft = "";
    state.result = null;
    state.actionReceipt = null;
    state.actionStatusConnectionInterrupted = false;
    state.errorCode = null;
    state.failure = null;
    state.streamingText = "";
    state.activityEvents = [];
    state.currentActivity = null;
    state.lastSubmittedMessage = "";
    state.taskPlanRequested = false;
    state.turnState = null;
    state.loading = false;
    state.decisionLoading = false;
    state.publicReferenceNotice = "";
    state.historyView = true;

    state.turnScopes =
        state.turnScopes && typeof state.turnScopes === "object" ? state.turnScopes : {};
    state.turnScopeSequence = Number.isSafeInteger(state.turnScopeSequence)
        ? state.turnScopeSequence + 1
        : 1;
    const key = `new:${state.turnScopeSequence}`;
    state.turnScopes[key] = createConversationTurnScope({ key });
    state.activeTurnScopeKey = key;
    return key;
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const service = super.start(env, dependencies);
        prepareFreshAssistantEntry(service.state);
        return service;
    },
});
