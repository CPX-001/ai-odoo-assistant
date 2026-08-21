/** @odoo-module **/

import { registry } from "@web/core/registry";
import { reactive } from "@odoo/owl";

const KNOWN_ERROR_CODES = new Set([
    "access_denied",
    "authentication_failed",
    "invalid_context",
    "invalid_response",
    "service_unavailable",
]);

export const assistantPanelService = {
    dependencies: ["odoo_ai_screen_context", "orm"],
    start(env, { odoo_ai_screen_context: screenContext, orm }) {
        const state = reactive({
            isOpen: false,
            loading: false,
            context: null,
            result: null,
            errorCode: null,
        });
        const refreshContext = () => {
            state.context = screenContext.capture();
            state.result = null;
            state.errorCode = null;
        };
        const open = () => {
            state.isOpen = true;
            refreshContext();
        };
        return {
            state,
            open,
            close() {
                state.isOpen = false;
            },
            toggle() {
                if (state.isOpen) {
                    state.isOpen = false;
                } else {
                    open();
                }
            },
            refreshContext,
            async submit(message) {
                refreshContext();
                if (!state.context?.model || !state.context?.res_id) {
                    state.errorCode = "invalid_context";
                    return;
                }
                state.loading = true;
                try {
                    const response = await orm.call(
                        "odoo.ai.assistant.bridge",
                        "submit_context_read",
                        [message, state.context]
                    );
                    if (response?.ok === true) {
                        state.result = response;
                        state.errorCode = null;
                    } else {
                        const code = response?.error?.code;
                        state.errorCode = KNOWN_ERROR_CODES.has(code)
                            ? code
                            : "invalid_response";
                        state.result = null;
                    }
                } catch {
                    state.errorCode = "service_unavailable";
                    state.result = null;
                } finally {
                    state.loading = false;
                }
            },
        };
    },
};

registry.category("services").add("odoo_ai_assistant_panel", assistantPanelService);
