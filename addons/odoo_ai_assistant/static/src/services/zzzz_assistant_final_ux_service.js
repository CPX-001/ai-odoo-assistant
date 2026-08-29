/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";
import {
    conversationScopeKey,
    projectConversationTurnScope,
} from "@odoo_ai_assistant/services/zzz_assistant_turn_scope_service";
import {
    finalTurnPresentation,
    reconcileFinalAssistantMessage,
} from "@odoo_ai_assistant/services/assistant_final_ux_contract";

function reconcileScope(scope) {
    const result = scope?.result;
    if (!result || typeof result.turn_id !== "string" || !result.turn_id) {
        return false;
    }
    const changed = reconcileFinalAssistantMessage(scope, {
        turnId: result.turn_id,
        answer: result.answer,
    });
    if (!scope.loading && scope.streamingText) {
        scope.streamingText = "";
        return true;
    }
    return changed;
}

export function reconcileFinalUxState(state) {
    let activeChanged = false;
    for (const scope of Object.values(state?.turnScopes || {})) {
        const changed = reconcileScope(scope);
        if (changed && scope.key === state.activeTurnScopeKey) {
            activeChanged = true;
        }
    }
    if (activeChanged) {
        const active = state.turnScopes?.[state.activeTurnScopeKey];
        if (active) {
            projectConversationTurnScope(state, active);
        }
    }
    return activeChanged;
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const service = super.start(env, dependencies);
        const state = service.state;
        const baseSubmit = service.submit.bind(service);

        service.submit = async (message) => {
            const submitted = await baseSubmit(message);
            reconcileFinalUxState(state);
            return submitted;
        };

        service.finalUxPresentation = (conversationId = state.conversationId) => {
            const key = conversationId
                ? conversationScopeKey(conversationId)
                : state.activeTurnScopeKey;
            const scope = key ? state.turnScopes?.[key] : null;
            return finalTurnPresentation(scope || state);
        };

        return service;
    },
});
