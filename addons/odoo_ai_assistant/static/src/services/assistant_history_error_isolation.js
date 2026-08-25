/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

/**
 * Auxiliary history loading must never create, replace, or clear a chat-turn error.
 * The history service may still update conversations/messages on success; only the
 * conversational error channel is preserved across the auxiliary operation.
 */
export async function withoutChatErrorSideEffect(state, operation) {
    const previousErrorCode = state.errorCode;
    try {
        return await operation();
    } finally {
        state.errorCode = previousErrorCode;
    }
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        const baseLoadHistory = panel.loadHistory.bind(panel);
        return {
            ...panel,
            loadHistory(...args) {
                return withoutChatErrorSideEffect(panel.state, () => baseLoadHistory(...args));
            },
        };
    },
});
