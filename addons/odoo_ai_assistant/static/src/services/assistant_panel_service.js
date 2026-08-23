/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { reactive } from "@odoo/owl";

export const ASSISTANT_WORKFLOWS = Object.freeze([
    "EXPLAIN",
    "QUERY",
    "HOW_TO",
    "ACTION",
]);

const WORKFLOW_CITATION_KINDS = Object.freeze({
    EXPLAIN: new Set(["record", "source"]),
    QUERY: new Set(["query"]),
    HOW_TO: new Set(["navigation", "schema", "document"]),
});

const KNOWN_ERROR_CODES = new Set([
    "access_denied",
    "action_budget_exceeded",
    "action_rejected",
    "approval_binding_mismatch",
    "approval_expired",
    "approval_not_found",
    "authentication_failed",
    "engine_timeout",
    "engine_unavailable",
    "evidence_unavailable",
    "invalid_context",
    "invalid_response",
    "invalid_workflow",
    "query_budget_exceeded",
    "query_rejected",
    "proposal_already_decided",
    "proposal_not_found",
    "record_context_required",
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
    if (expectedWorkflow === "ACTION") {
        return normalizeActionResponse(response);
    }
    const validWorkflow = ASSISTANT_WORKFLOWS.includes(expectedWorkflow);
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

function exactKeys(value, expected) {
    return (
        value !== null &&
        typeof value === "object" &&
        Object.keys(value).sort().join("|") === [...expected].sort().join("|")
    );
}

function validActionValue(value) {
    if (!exactKeys(value, ["kind", "value"])) {
        return false;
    }
    const item = value.value;
    if (item === null) {
        return true;
    }
    if (value.kind === "boolean") {
        return typeof item === "boolean";
    }
    if (value.kind === "integer") {
        return Number.isSafeInteger(item);
    }
    if (value.kind === "many2one") {
        return Number.isSafeInteger(item) && item > 0;
    }
    return (
        ["date", "datetime", "decimal", "selection", "text"].includes(value.kind) &&
        typeof item === "string" &&
        item.length <= 4000
    );
}

function validActionProposal(proposal) {
    if (proposal?.action_kind === "business_action") {
        return (
            exactKeys(proposal, [
                "action_id",
                "action_kind",
                "display_name",
                "expected_states",
                "expires_at",
                "proposal_id",
                "state_before",
                "target",
                "warnings",
            ]) &&
            proposal.action_id === "sale.order.confirm.v1" &&
            typeof proposal.proposal_id === "string" &&
            exactKeys(proposal.target, ["model", "record_id"]) &&
            proposal.target.model === "sale.order" &&
            Number.isSafeInteger(proposal.target.record_id) &&
            proposal.target.record_id > 0 &&
            typeof proposal.display_name === "string" &&
            proposal.display_name.length > 0 &&
            proposal.display_name.length <= 256 &&
            ["draft", "sent"].includes(proposal.state_before) &&
            Array.isArray(proposal.expected_states) &&
            proposal.expected_states.join("|") === "sale|done" &&
            Array.isArray(proposal.warnings) &&
            proposal.warnings.length <= 8 &&
            proposal.warnings.every(
                (value) => typeof value === "string" && value.length > 0 && value.length <= 512
            ) &&
            typeof proposal.expires_at === "string"
        );
    }
    if (proposal?.action_kind === "record_create") {
        if (
            !exactKeys(proposal, [
                "action_kind",
                "proposal_id",
                "target",
                "values",
                "warnings",
                "expires_at",
            ]) ||
            typeof proposal.proposal_id !== "string" ||
            !exactKeys(proposal.target, ["model"]) ||
            typeof proposal.target.model !== "string" ||
            !Array.isArray(proposal.values) ||
            proposal.values.length < 1 ||
            proposal.values.length > 4 ||
            !Array.isArray(proposal.warnings) ||
            proposal.warnings.length > 8 ||
            !proposal.warnings.every(
                (value) => typeof value === "string" && value.length > 0 && value.length <= 512
            ) ||
            typeof proposal.expires_at !== "string"
        ) {
            return false;
        }
        const fields = new Set();
        for (const value of proposal.values) {
            if (
                !exactKeys(value, ["field", "label", "value"]) ||
                typeof value.field !== "string" ||
                value.field.length < 1 ||
                value.field.length > 128 ||
                (value.label !== null &&
                    (typeof value.label !== "string" || value.label.length > 256)) ||
                !validActionValue(value.value) ||
                fields.has(value.field)
            ) {
                return false;
            }
            fields.add(value.field);
        }
        return true;
    }
    if (
        !exactKeys(proposal, [
            "proposal_id",
            "target",
            "changes",
            "warnings",
            "expires_at",
        ]) ||
        typeof proposal.proposal_id !== "string" ||
        proposal.proposal_id.length > 64 ||
        !exactKeys(proposal.target, ["model", "record_id"]) ||
        typeof proposal.target.model !== "string" ||
        !Number.isSafeInteger(proposal.target.record_id) ||
        proposal.target.record_id <= 0 ||
        !Array.isArray(proposal.changes) ||
        proposal.changes.length < 1 ||
        proposal.changes.length > 4 ||
        !Array.isArray(proposal.warnings) ||
        proposal.warnings.length > 8 ||
        !proposal.warnings.every(
            (value) => typeof value === "string" && value.length > 0 && value.length <= 512
        ) ||
        typeof proposal.expires_at !== "string"
    ) {
        return false;
    }
    const fields = new Set();
    for (const change of proposal.changes) {
        if (
            !exactKeys(change, ["field", "label", "before", "after"]) ||
            typeof change.field !== "string" ||
            change.field.length < 1 ||
            change.field.length > 128 ||
            (change.label !== null &&
                (typeof change.label !== "string" || change.label.length > 256)) ||
            !validActionValue(change.before) ||
            !validActionValue(change.after) ||
            fields.has(change.field)
        ) {
            return false;
        }
        fields.add(change.field);
    }
    return true;
}

export function normalizeActionResponse(response) {
    const proposal = response?.proposal;
    if (
        exactKeys(response, [
            "ok",
            "turn_id",
            "workflow",
            "answer",
            "confidence",
            "limitations",
            "proposal",
        ]) &&
        response.ok === true &&
        response.workflow === "ACTION" &&
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
        (proposal === null || validActionProposal(proposal))
    ) {
        return { result: response, errorCode: null };
    }
    const code = response?.error?.code;
    return {
        result: null,
        errorCode: KNOWN_ERROR_CODES.has(code) ? code : "invalid_response",
    };
}

export function normalizeActionDecisionResponse(response, proposalId) {
    const states = new Set([
        "rejected",
        "verified",
        "stale",
        "failed",
        "execution_unknown",
        "committed_unverified",
    ]);
    if (
        exactKeys(response, [
            "ok",
            "proposal_id",
            "state",
            "completed_at",
            "approval_id",
            "attempt_id",
            "evidence_id",
            "error_code",
        ]) &&
        response.ok === true &&
        response.proposal_id === proposalId &&
        states.has(response.state) &&
        typeof response.completed_at === "string" &&
        (response.approval_id === null || typeof response.approval_id === "string") &&
        (response.attempt_id === null || typeof response.attempt_id === "string") &&
        (response.evidence_id === null || typeof response.evidence_id === "string") &&
        (response.error_code === null || typeof response.error_code === "string") &&
        (response.state !== "verified" || response.evidence_id !== null)
    ) {
        return { receipt: response, errorCode: null };
    }
    const code = response?.error?.code;
    return {
        receipt: null,
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
    if (workflow === "ACTION") {
        return Boolean(context?.model && context?.res_id);
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
    if (state.loading || state.decisionLoading) {
        return false;
    }
    if (!ASSISTANT_WORKFLOWS.includes(workflow)) {
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
    state.actionReceipt = null;
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

export async function submitActionDecision({ state, rpcCall, decision }) {
    const proposalId = state.result?.proposal?.proposal_id;
    if (
        state.loading ||
        state.decisionLoading ||
        typeof proposalId !== "string" ||
        !["approve", "reject"].includes(decision)
    ) {
        return false;
    }
    state.decisionLoading = true;
    state.errorCode = null;
    try {
        const response = await rpcCall("/odoo_ai/v1/action-decision", {
            proposal_id: proposalId,
            decision,
        });
        const normalized = normalizeActionDecisionResponse(response, proposalId);
        state.actionReceipt = normalized.receipt;
        state.errorCode = normalized.errorCode;
    } catch {
        state.actionReceipt = null;
        state.errorCode = "service_unavailable";
    } finally {
        state.decisionLoading = false;
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
            decisionLoading: false,
            workflow: "EXPLAIN",
            context: null,
            result: null,
            actionReceipt: null,
            errorCode: null,
        });
        const refreshContext = () => {
            state.context = screenContext.capture();
            state.result = null;
            state.actionReceipt = null;
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
                if (
                    !ASSISTANT_WORKFLOWS.includes(workflow) ||
                    state.loading ||
                    state.decisionLoading
                ) {
                    return false;
                }
                state.workflow = workflow;
                state.result = null;
                state.actionReceipt = null;
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
            async decide(decision) {
                return submitActionDecision({ state, rpcCall: rpc, decision });
            },
        };
    },
};

registry.category("services").add("odoo_ai_assistant_panel", assistantPanelService);
