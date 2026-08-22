/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { reactive } from "@odoo/owl";

const KNOWN_ERROR_CODES = new Set([
    "access_denied",
    "authentication_failed",
    "engine_timeout",
    "engine_unavailable",
    "evidence_unavailable",
    "invalid_context",
    "invalid_response",
    "service_unavailable",
]);

export function normalizeExplainResponse(response) {
    if (
        response?.ok === true &&
        typeof response.turn_id === "string" &&
        typeof response.answer === "string" &&
        ["high", "medium", "low"].includes(response.confidence) &&
        Array.isArray(response.limitations) &&
        Array.isArray(response.citations)
    ) {
        return { result: response, errorCode: null };
    }
    const code = response?.error?.code;
    return {
        result: null,
        errorCode: KNOWN_ERROR_CODES.has(code) ? code : "invalid_response",
    };
}

export async function submitExplainRequest({ state, screenContext, rpcCall, message }) {
    if (state.loading) {
        return false;
    }
    state.context = screenContext.capture();
    state.result = null;
    state.errorCode = null;
    if (!state.context?.model || !state.context?.res_id) {
        state.errorCode = "invalid_context";
        return false;
    }
    state.loading = true;
    try {
        const response = await rpcCall("/odoo_ai/v1/explain", {
            message,
            screen: state.context,
        });
        const normalized = normalizeExplainResponse(response);
        state.result = normalized.result;
        state.errorCode = normalized.errorCode;
    } catch {
        state.errorCode = "service_unavailable";
        state.result = null;
    } finally {
        state.loading = false;
    }
    return true;
}

export const assistantPanelService = {
    dependencies: ["odoo_ai_screen_context"],
    start(env, { odoo_ai_screen_context: screenContext }) {
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
                return submitExplainRequest({
                    state,
                    screenContext,
                    rpcCall: rpc,
                    message,
                });
            },
        };
    },
};

registry.category("services").add("odoo_ai_assistant_panel", assistantPanelService);
