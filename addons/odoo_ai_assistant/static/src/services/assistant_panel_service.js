/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { reactive } from "@odoo/owl";

export const READ_ONLY_WORKFLOWS = Object.freeze(["EXPLAIN", "QUERY", "HOW_TO"]);

const WORKFLOW_CITATION_KINDS = Object.freeze({
    EXPLAIN: new Set(["record", "source"]),
    QUERY: new Set(["query"]),
    HOW_TO: new Set(["navigation", "schema", "document"]),
});

const KNOWN_ERROR_CODES = new Set([
    "access_denied",
    "authentication_failed",
    "engine_timeout",
    "engine_unavailable",
    "evidence_unavailable",
    "invalid_context",
    "invalid_response",
    "invalid_workflow",
    "query_budget_exceeded",
    "query_rejected",
    "service_unavailable",
]);

function validCitation(citation, workflow) {
    return (
        citation !== null &&
        typeof citation === "object" &&
        typeof citation.evidence_id === "string" &&
        citation.evidence_id.length <= 64 &&
        WORKFLOW_CITATION_KINDS[workflow].has(citation.kind)
    );
}

export function normalizeWorkflowResponse(response, expectedWorkflow) {
    const validWorkflow = READ_ONLY_WORKFLOWS.includes(expectedWorkflow);
    const citations = response?.citations;
    if (
        validWorkflow &&
        response?.ok === true &&
        response.workflow === expectedWorkflow &&
        typeof response.turn_id === "string" &&
        typeof response.answer === "string" &&
        response.answer.length > 0 &&
        response.answer.length <= 16384 &&
        ["high", "medium", "low"].includes(response.confidence) &&
        Array.isArray(response.limitations) &&
        response.limitations.length <= 8 &&
        response.limitations.every(
            (value) =>
                typeof value === "string" && value.length > 0 && value.length <= 1024
        ) &&
        Array.isArray(citations) &&
        citations.length <= 24 &&
        citations.every((citation) => validCitation(citation, expectedWorkflow)) &&
        new Set(citations.map((citation) => citation.evidence_id)).size === citations.length
    ) {
        return { result: response, errorCode: null };
    }
    const code = response?.error?.code;
    return {
        result: null,
        errorCode: KNOWN_ERROR_CODES.has(code) ? code : "invalid_response",
    };
}

export function normalizeExplainResponse(response) {
    return normalizeWorkflowResponse(response, "EXPLAIN");
}

function contextSupportsWorkflow(context, workflow) {
    if (workflow === "HOW_TO") {
        return Boolean(context);
    }
    if (workflow === "QUERY") {
        return Boolean(context?.model);
    }
    return Boolean(context?.model && context?.res_id);
}

export async function submitAssistantRequest({
    state,
    screenContext,
    rpcCall,
    message,
    workflow = state.workflow,
}) {
    if (state.loading) {
        return false;
    }
    if (!READ_ONLY_WORKFLOWS.includes(workflow)) {
        state.result = null;
        state.errorCode = "invalid_workflow";
        return false;
    }
    if (typeof message !== "string" || !message.trim() || message.length > 4000) {
        state.result = null;
        state.errorCode = "invalid_context";
        return false;
    }
    state.context = screenContext.capture();
    state.result = null;
    state.errorCode = null;
    if (!contextSupportsWorkflow(state.context, workflow)) {
        state.errorCode = "invalid_context";
        return false;
    }
    state.loading = true;
    try {
        const response = await rpcCall("/odoo_ai/v1/turn", {
            message,
            screen: state.context,
            workflow,
        });
        const normalized = normalizeWorkflowResponse(response, workflow);
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

export async function submitExplainRequest(options) {
    return submitAssistantRequest({ ...options, workflow: "EXPLAIN" });
}

export const assistantPanelService = {
    dependencies: ["odoo_ai_screen_context"],
    start(env, { odoo_ai_screen_context: screenContext }) {
        const state = reactive({
            isOpen: false,
            loading: false,
            workflow: "EXPLAIN",
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
            setWorkflow(workflow) {
                if (!READ_ONLY_WORKFLOWS.includes(workflow) || state.loading) {
                    return false;
                }
                state.workflow = workflow;
                state.result = null;
                state.errorCode = null;
                return true;
            },
            refreshContext,
            async submit(message) {
                return submitAssistantRequest({
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
