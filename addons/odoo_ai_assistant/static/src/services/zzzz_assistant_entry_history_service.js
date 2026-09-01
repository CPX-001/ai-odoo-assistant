/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import {
    assistantPanelService,
    resetForNewConversation,
} from "@odoo_ai_assistant/services/assistant_panel_service";
import { clearRecentActiveChat } from "@odoo_ai_assistant/services/assistant_history_service";
import { createConversationTurnScope } from "@odoo_ai_assistant/services/zzz_assistant_turn_scope_service";

function browserSessionStorage() {
    try {
        return globalThis.sessionStorage || null;
    } catch {
        return null;
    }
}

function browserLocalStorage() {
    try {
        return globalThis.localStorage || null;
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
    { sessionStorage = browserSessionStorage(), localStorage = browserLocalStorage() } = {}
) {
    clearRecentActiveChat(sessionStorage);
    resetForNewConversation(state, localStorage);
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
