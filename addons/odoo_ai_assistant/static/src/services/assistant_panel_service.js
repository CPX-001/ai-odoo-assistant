/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { reactive } from "@odoo/owl";

const CHAT_WORKFLOWS = new Set(["GENERAL", "EXPLAIN", "QUERY", "HOW_TO", "ACTION"]);
const KNOWN_ERROR_CODES = new Set([
    "access_denied",
    "action_budget_exceeded",
    "action_rejected",
    "approval_binding_mismatch",
    "approval_expired",
    "approval_not_found",
    "authentication_failed",
    "chat_store_unavailable",
    "engine_timeout",
    "engine_unavailable",
    "evidence_unavailable",
    "invalid_context",
    "invalid_response",
    "query_budget_exceeded",
    "query_rejected",
    "proposal_already_decided",
    "proposal_not_found",
    "record_context_required",
    "service_unavailable",
]);

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
    if (proposal === null || proposal === undefined) {
        return true;
    }
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
            ["draft", "sent"].includes(proposal.state_before) &&
            Array.isArray(proposal.expected_states) &&
            proposal.expected_states.join("|") === "sale|done" &&
            Array.isArray(proposal.warnings) &&
            proposal.warnings.length <= 8 &&
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
            typeof proposal.expires_at !== "string"
        ) {
            return false;
        }
        const fields = new Set();
        for (const value of proposal.values) {
            if (
                !exactKeys(value, ["field", "label", "value"]) ||
                typeof value.field !== "string" ||
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
        !exactKeys(proposal.target, ["model", "record_id"]) ||
        typeof proposal.target.model !== "string" ||
        !Number.isSafeInteger(proposal.target.record_id) ||
        proposal.target.record_id <= 0 ||
        !Array.isArray(proposal.changes) ||
        proposal.changes.length < 1 ||
        proposal.changes.length > 4 ||
        !Array.isArray(proposal.warnings) ||
        proposal.warnings.length > 8 ||
        typeof proposal.expires_at !== "string"
    ) {
        return false;
    }
    const fields = new Set();
    for (const change of proposal.changes) {
        if (
            !exactKeys(change, ["field", "label", "before", "after"]) ||
            typeof change.field !== "string" ||
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

function validCitation(value) {
    return (
        value !== null &&
        typeof value === "object" &&
        typeof value.evidence_id === "string" &&
        value.evidence_id.length <= 64 &&
        typeof value.kind === "string"
    );
}

export function normalizeChatResponse(response) {
    const limitations = response?.limitations;
    const citations = response?.citations || [];
    const proposal = response?.proposal ?? null;
    if (
        response?.ok === true &&
        typeof response.turn_id === "string" &&
        CHAT_WORKFLOWS.has(response.workflow) &&
        typeof response.answer === "string" &&
        response.answer.length > 0 &&
        response.answer.length <= 16384 &&
        ["high", "medium", "low"].includes(response.confidence) &&
        Array.isArray(limitations) &&
        limitations.length <= 8 &&
        limitations.every(
            (value) => typeof value === "string" && value.length > 0 && value.length <= 1024
        ) &&
        Array.isArray(citations) &&
        citations.length <= 24 &&
        citations.every(validCitation) &&
        validActionProposal(proposal) &&
        (response.conversation_id === null ||
            response.conversation_id === undefined ||
            typeof response.conversation_id === "string")
    ) {
        return {
            result: { ...response, citations, proposal },
            errorCode: null,
        };
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

export function normalizeHistoryResponse(response) {
    if (
        response?.ok === true &&
        (response.active_conversation_id === null ||
            typeof response.active_conversation_id === "string") &&
        Array.isArray(response.conversations) &&
        response.conversations.length <= 50 &&
        response.conversations.every(
            (item) =>
                typeof item?.conversation_id === "string" &&
                typeof item?.title === "string" &&
                typeof item?.updated_at === "string"
        ) &&
        Array.isArray(response.messages) &&
        response.messages.length <= 80 &&
        response.messages.every(
            (item) =>
                typeof item?.message_id === "string" &&
                ["user", "assistant"].includes(item?.role) &&
                typeof item?.content === "string" &&
                typeof item?.created_at === "string"
        )
    ) {
        return { history: response, errorCode: null };
    }
    const code = response?.error?.code;
    return {
        history: null,
        errorCode: KNOWN_ERROR_CODES.has(code) ? code : "invalid_response",
    };
}

function browserStorage() {
    try {
        return globalThis.localStorage || null;
    } catch {
        return null;
    }
}

export function draftStorageKey(conversationId) {
    const host = globalThis.location?.host || "odoo";
    const uid =
        globalThis.odoo?.session_info?.uid ??
        globalThis.odoo?.__session_info__?.uid;
    const userScope = Number.isSafeInteger(uid) && uid > 0 ? String(uid) : "session";
    return `odoo_ai_assistant:draft:${host}:${userScope}:${conversationId || "new"}`;
}

export function loadDraft(storage, conversationId) {
    try {
        const value = storage?.getItem(draftStorageKey(conversationId));
        return typeof value === "string" ? value.slice(0, 4000) : "";
    } catch {
        return "";
    }
}

export function saveDraft(storage, conversationId, value) {
    try {
        storage?.setItem(draftStorageKey(conversationId), String(value || "").slice(0, 4000));
        return true;
    } catch {
        return false;
    }
}

export async function submitAssistantRequest({ state, screenContext, rpcCall, message }) {
    if (state.loading || state.decisionLoading) {
        return false;
    }
    const normalized = typeof message === "string" ? message.trim() : "";
    if (!normalized || normalized.length > 4000) {
        state.errorCode = "invalid_context";
        return false;
    }
    state.context = screenContext.capture();
    state.loading = true;
    state.errorCode = null;
    state.actionReceipt = null;
    try {
        const response = await rpcCall("/odoo_ai/v1/chat", {
            message: normalized,
            screen: state.context,
            conversation_id: state.conversationId,
        });
        const parsed = normalizeChatResponse(response);
        state.result = parsed.result;
        state.errorCode = parsed.errorCode;
        if (parsed.result) {
            const previousConversationId = state.conversationId;
            state.conversationId = parsed.result.conversation_id || state.conversationId;
            if (
                state.conversationId &&
                !state.conversations.some(
                    (item) => item.conversation_id === state.conversationId
                )
            ) {
                const now = new Date().toISOString();
                state.conversations = [
                    {
                        conversation_id: state.conversationId,
                        title: normalized.slice(0, 160),
                        created_at: now,
                        updated_at: now,
                    },
                    ...state.conversations,
                ];
            } else if (state.conversationId && previousConversationId === state.conversationId) {
                state.conversations = state.conversations.map((item) =>
                    item.conversation_id === state.conversationId
                        ? { ...item, updated_at: new Date().toISOString() }
                        : item
                );
            }
            state.messages = [
                ...state.messages,
                {
                    message_id: `local-user-${parsed.result.turn_id}`,
                    role: "user",
                    content: normalized,
                    created_at: new Date().toISOString(),
                },
                {
                    message_id: `local-assistant-${parsed.result.turn_id}`,
                    role: "assistant",
                    content: parsed.result.answer,
                    created_at: new Date().toISOString(),
                },
            ];
        }
    } catch {
        state.result = null;
        state.errorCode = "service_unavailable";
    } finally {
        state.loading = false;
    }
    return state.result !== null;
}

export async function loadChatHistory({ state, rpcCall, conversationId = state.conversationId }) {
    if (state.historyLoading) {
        return false;
    }
    state.historyLoading = true;
    try {
        const response = await rpcCall("/odoo_ai/v1/chat-history", {
            conversation_id: conversationId,
        });
        const parsed = normalizeHistoryResponse(response);
        if (!parsed.history) {
            state.errorCode = parsed.errorCode;
            return false;
        }
        state.conversations = parsed.history.conversations;
        state.conversationId = parsed.history.active_conversation_id;
        state.messages = parsed.history.messages;
        state.errorCode = null;
        return true;
    } catch {
        state.errorCode = "service_unavailable";
        return false;
    } finally {
        state.historyLoading = false;
    }
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

export const assistantPanelService = {
    dependencies: ["odoo_ai_screen_context"],
    start(env, { odoo_ai_screen_context: screenContext }) {
        const storage = browserStorage();
        const state = reactive({
            isOpen: false,
            loading: false,
            historyLoading: false,
            decisionLoading: false,
            context: null,
            conversations: [],
            conversationId: null,
            messages: [],
            draft: loadDraft(storage, null),
            result: null,
            actionReceipt: null,
            errorCode: null,
        });
        const refreshContext = () => {
            state.context = screenContext.capture();
        };
        const syncDraft = () => {
            state.draft = loadDraft(storage, state.conversationId);
        };
        const loadHistory = async (conversationId = state.conversationId) => {
            const loaded = await loadChatHistory({ state, rpcCall: rpc, conversationId });
            if (loaded) {
                syncDraft();
            }
            return loaded;
        };
        const open = () => {
            state.isOpen = true;
            refreshContext();
            void loadHistory();
        };
        return {
            state,
            open,
            close() {
                saveDraft(storage, state.conversationId, state.draft);
                state.isOpen = false;
            },
            toggle() {
                if (state.isOpen) {
                    saveDraft(storage, state.conversationId, state.draft);
                    state.isOpen = false;
                } else {
                    open();
                }
            },
            refreshContext,
            loadHistory,
            newConversation() {
                saveDraft(storage, state.conversationId, state.draft);
                state.conversationId = null;
                state.messages = [];
                state.result = null;
                state.actionReceipt = null;
                state.errorCode = null;
                syncDraft();
            },
            async selectConversation(conversationId) {
                if (state.loading || state.decisionLoading || !conversationId) {
                    return false;
                }
                saveDraft(storage, state.conversationId, state.draft);
                state.result = null;
                state.actionReceipt = null;
                return loadHistory(conversationId);
            },
            setDraft(value) {
                state.draft = String(value || "").slice(0, 4000);
                saveDraft(storage, state.conversationId, state.draft);
            },
            async submit(message) {
                const draftConversationId = state.conversationId;
                const sent = await submitAssistantRequest({
                    state,
                    screenContext,
                    rpcCall: rpc,
                    message,
                });
                if (sent) {
                    state.draft = "";
                    saveDraft(storage, draftConversationId, "");
                    saveDraft(storage, state.conversationId, "");
                }
                return sent;
            },
            async decide(decision) {
                return submitActionDecision({ state, rpcCall: rpc, decision });
            },
        };
    },
};

registry.category("services").add("odoo_ai_assistant_panel", assistantPanelService);
