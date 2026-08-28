/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import {
    assistantPanelService,
    loadChatHistory,
    loadDraft,
    normalizeChatResponse,
    recoveryPending,
    resetForNewConversation,
    saveDraft,
    submitActionDecision,
    submitActionRetry,
} from "@odoo_ai_assistant/services/assistant_panel_service";
import {
    AssistantFailureError,
    failureCanRetry,
    failureFromError,
} from "@odoo_ai_assistant/services/assistant_failure_contract";
import { streamAssistantChatLive } from "@odoo_ai_assistant/services/assistant_live_stream_client";
import {
    clearRecentActiveChat,
    loadRecentActiveChat,
    saveRecentActiveChat,
} from "@odoo_ai_assistant/services/assistant_history_service";

const CONVERSATION_KEY_PREFIX = "conversation:";
const NEW_KEY_PREFIX = "new:";
const RUNTIME_STATE_LABELS = Object.freeze({
    queued: "En cola",
    running: "En curso",
    awaiting_approval: "Esperando aprobación",
    failed: "Falló",
    recovery: "Revisar recuperación",
    completed: "Completado",
});
let pendingMessageSequence = 0;

function browserLocalStorage() {
    try {
        return globalThis.localStorage || null;
    } catch {
        return null;
    }
}

function browserSessionStorage() {
    try {
        return globalThis.sessionStorage || null;
    } catch {
        return null;
    }
}

function pendingMessageId() {
    pendingMessageSequence += 1;
    return `local-user-pending-${Date.now()}-${pendingMessageSequence}`;
}

export function conversationScopeKey(conversationId) {
    return typeof conversationId === "string" && conversationId
        ? `${CONVERSATION_KEY_PREFIX}${conversationId}`
        : null;
}

export function createConversationTurnScope({ key, conversationId = null } = {}) {
    if (typeof key !== "string" || !key) {
        throw new Error("invalid_scope_key");
    }
    return {
        key,
        conversationId,
        turnId: null,
        turnState: null,
        loading: false,
        decisionLoading: false,
        result: null,
        actionReceipt: null,
        errorCode: null,
        failure: null,
        streamingText: "",
        activityEvents: [],
        currentActivity: null,
        lastSubmittedMessage: "",
        messages: [],
    };
}

function nextNewScopeKey(state) {
    state.turnScopeSequence = Number.isSafeInteger(state.turnScopeSequence)
        ? state.turnScopeSequence + 1
        : 1;
    return `${NEW_KEY_PREFIX}${state.turnScopeSequence}`;
}

function ensureScope(state, key, conversationId = null) {
    if (!state.turnScopes[key]) {
        state.turnScopes[key] = createConversationTurnScope({ key, conversationId });
    }
    return state.turnScopes[key];
}

function activeScope(state) {
    return ensureScope(state, state.activeTurnScopeKey, state.conversationId || null);
}

function copyVisibleIntoScope(state, scope) {
    scope.loading = Boolean(state.loading);
    scope.decisionLoading = Boolean(state.decisionLoading);
    scope.result = state.result || null;
    scope.actionReceipt = state.actionReceipt || null;
    scope.errorCode = state.errorCode || null;
    scope.failure = state.failure || null;
    scope.streamingText = state.streamingText || "";
    scope.activityEvents = Array.isArray(state.activityEvents) ? [...state.activityEvents] : [];
    scope.currentActivity = state.currentActivity || null;
    scope.lastSubmittedMessage = state.lastSubmittedMessage || "";
    scope.messages = Array.isArray(state.messages) ? [...state.messages] : [];
}

export function projectConversationTurnScope(state, scope) {
    state.loading = Boolean(scope.loading);
    state.decisionLoading = Boolean(scope.decisionLoading);
    state.result = scope.result || null;
    state.actionReceipt = scope.actionReceipt || null;
    state.errorCode = scope.errorCode || null;
    state.failure = scope.failure || null;
    state.streamingText = scope.streamingText || "";
    state.activityEvents = Array.isArray(scope.activityEvents) ? [...scope.activityEvents] : [];
    state.currentActivity = scope.currentActivity || null;
    state.lastSubmittedMessage = scope.lastSubmittedMessage || "";
    state.messages = Array.isArray(scope.messages) ? [...scope.messages] : [];
    return scope;
}

function projectIfActive(state, scope) {
    if (state.activeTurnScopeKey === scope.key) {
        projectConversationTurnScope(state, scope);
    }
}

export function bindConversationTurnScope(state, scope, { conversationId, turnId, turnState }) {
    const nextKey = conversationScopeKey(conversationId);
    if (!nextKey || typeof turnId !== "string" || !turnId) {
        throw new Error("invalid_turn_binding");
    }
    if (scope.conversationId && scope.conversationId !== conversationId) {
        throw new Error("conversation_binding_mismatch");
    }
    const previousKey = scope.key;
    scope.key = nextKey;
    scope.conversationId = conversationId;
    scope.turnId = turnId;
    scope.turnState = turnState || scope.turnState || "queued";
    if (previousKey !== nextKey) {
        delete state.turnScopes[previousKey];
    }
    state.turnScopes[nextKey] = scope;
    if (state.activeTurnScopeKey === previousKey) {
        state.activeTurnScopeKey = nextKey;
        state.conversationId = conversationId;
    }
    return scope;
}

export function conversationRuntimeState(scope) {
    if (!scope) {
        return null;
    }
    if (
        scope.actionReceipt?.state === "recovery_required" ||
        ["authorized", "executing"].includes(scope.result?.plan?.state) ||
        scope.turnState === "recovery_required"
    ) {
        return "recovery";
    }
    if (
        scope.result?.plan?.state === "awaiting_confirmation" ||
        scope.turnState === "awaiting_confirmation"
    ) {
        return "awaiting_approval";
    }
    if (scope.loading) {
        return scope.turnState === "queued" ? "queued" : "running";
    }
    if (scope.failure || scope.errorCode || scope.turnState === "failed") {
        return "failed";
    }
    if (["completed", "cancelled"].includes(scope.turnState)) {
        return "completed";
    }
    return null;
}

export function conversationRuntimeLabel(scope) {
    return RUNTIME_STATE_LABELS[conversationRuntimeState(scope)] || "";
}

function updateConversationList(state, scope, title = null) {
    if (!scope.conversationId) {
        return;
    }
    const now = new Date().toISOString();
    const runtimeState = conversationRuntimeState(scope);
    const existing = state.conversations.find(
        (item) => item.conversation_id === scope.conversationId
    );
    if (!existing) {
        state.conversations = [
            {
                conversation_id: scope.conversationId,
                title: title || "Nueva conversación",
                created_at: now,
                updated_at: now,
                runtime_state: runtimeState,
                runtime_turn_id: scope.turnId,
            },
            ...state.conversations,
        ];
        return;
    }
    state.conversations = state.conversations.map((item) =>
        item.conversation_id === scope.conversationId
            ? {
                  ...item,
                  updated_at: now,
                  runtime_state: runtimeState,
                  runtime_turn_id: scope.turnId,
              }
            : item
    );
}

function decorateConversationRuntime(state) {
    state.conversations = (state.conversations || []).map((item) => {
        const key = conversationScopeKey(item.conversation_id);
        const scope = key ? state.turnScopes[key] : null;
        if (!scope) {
            return item;
        }
        return {
            ...item,
            runtime_state: conversationRuntimeState(scope),
            runtime_turn_id: scope.turnId,
        };
    });
}

function appendActivity(scope, event) {
    if (!event || !Number.isSafeInteger(event.sequence)) {
        throw new AssistantFailureError("invalid_response");
    }
    if (scope.activityEvents.some((item) => item.sequence === event.sequence)) {
        return;
    }
    scope.activityEvents = [...scope.activityEvents, event].slice(-100);
    scope.currentActivity = event;
}

async function bindPersistedTurn(state, scope, turnId, title) {
    const status = await rpc("/odoo_ai/v1/turn/status", {
        turn_id: turnId,
        after_sequence: 0,
    });
    if (
        status?.ok !== true ||
        status.turn_id !== turnId ||
        typeof status.conversation_id !== "string" ||
        !status.conversation_id
    ) {
        throw new AssistantFailureError("invalid_response");
    }
    bindConversationTurnScope(state, scope, {
        conversationId: status.conversation_id,
        turnId,
        turnState: status.state,
    });
    updateConversationList(state, scope, title);
    projectIfActive(state, scope);
}

async function submitScopedTurn({ state, screenContext, scope, message }) {
    if (scope.loading || scope.decisionLoading || recoveryPending(scope)) {
        return false;
    }
    const normalized = typeof message === "string" ? message.trim() : "";
    if (!normalized || normalized.length > 4000) {
        scope.failure = null;
        scope.errorCode = "invalid_context";
        projectIfActive(state, scope);
        return false;
    }

    state.context = screenContext.capture();
    scope.loading = true;
    scope.turnState = "queued";
    scope.streamingText = "";
    scope.activityEvents = [];
    scope.currentActivity = null;
    scope.errorCode = null;
    scope.failure = null;
    scope.actionReceipt = null;
    scope.lastSubmittedMessage = normalized;
    scope.messages = [
        ...scope.messages,
        {
            message_id: pendingMessageId(),
            role: "user",
            content: normalized,
            created_at: new Date().toISOString(),
        },
    ];
    projectIfActive(state, scope);

    try {
        const response = await streamAssistantChatLive({
            payload: {
                message: normalized,
                screen: state.context,
                conversation_id: scope.conversationId,
            },
            onTiming: async (timing) => {
                if (
                    timing?.point === "turn_persisted" &&
                    typeof timing.turn_id === "string" &&
                    !scope.turnId
                ) {
                    scope.turnId = timing.turn_id;
                    try {
                        await bindPersistedTurn(
                            state,
                            scope,
                            timing.turn_id,
                            normalized.slice(0, 160)
                        );
                    } catch {
                        // The final validated response also carries the conversation binding.
                        // A transient status read must not fail an otherwise durable turn.
                        projectIfActive(state, scope);
                    }
                }
            },
            onActivity: async (event) => {
                appendActivity(scope, event);
                if (scope.turnState === "queued") {
                    scope.turnState = "running";
                }
                updateConversationList(state, scope);
                projectIfActive(state, scope);
            },
            onDelta: async (text) => {
                if (typeof text !== "string" || !text) {
                    throw new AssistantFailureError("invalid_response");
                }
                const next = `${scope.streamingText || ""}${text}`;
                if (next.length > 16384) {
                    throw new AssistantFailureError("invalid_response");
                }
                scope.streamingText = next;
                if (scope.turnState === "queued") {
                    scope.turnState = "running";
                }
                updateConversationList(state, scope);
                projectIfActive(state, scope);
            },
        });
        const parsed = normalizeChatResponse(response);
        scope.streamingText = "";
        scope.result = parsed.result;
        scope.errorCode = parsed.errorCode;
        scope.failure = null;
        if (!parsed.result) {
            scope.turnState = "failed";
            updateConversationList(state, scope);
            projectIfActive(state, scope);
            return false;
        }
        scope.turnId = parsed.result.turn_id || scope.turnId;
        if (
            parsed.result.conversation_id &&
            scope.conversationId !== parsed.result.conversation_id
        ) {
            bindConversationTurnScope(state, scope, {
                conversationId: parsed.result.conversation_id,
                turnId: scope.turnId,
                turnState: scope.turnState,
            });
        }
        scope.turnState =
            parsed.result.plan?.state === "awaiting_confirmation"
                ? "awaiting_confirmation"
                : "completed";
        scope.messages = [
            ...scope.messages,
            {
                message_id: `local-assistant-${parsed.result.turn_id}`,
                role: "assistant",
                content: parsed.result.answer,
                created_at: new Date().toISOString(),
            },
        ];
        updateConversationList(state, scope);
        projectIfActive(state, scope);
        return true;
    } catch (error) {
        const parsed = failureFromError(error);
        scope.streamingText = "";
        scope.result = null;
        scope.errorCode = parsed.code;
        scope.failure = parsed.failure;
        scope.turnState = scope.turnState === "recovery_required" ? scope.turnState : "failed";
        updateConversationList(state, scope);
        projectIfActive(state, scope);
        return false;
    } finally {
        scope.loading = false;
        updateConversationList(state, scope);
        projectIfActive(state, scope);
    }
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const service = super.start(env, dependencies);
        const state = service.state;
        const localStorage = browserLocalStorage();
        const sessionStorage = browserSessionStorage();
        const baseOpen = service.open.bind(service);
        const baseClose = service.close.bind(service);
        const baseRefreshRuntimeAccount = service.refreshRuntimeAccount?.bind(service);

        state.turnScopes = {};
        state.turnScopeSequence = 0;
        state.activeTurnScopeKey =
            conversationScopeKey(state.conversationId) || nextNewScopeKey(state);
        const initialScope = activeScope(state);
        copyVisibleIntoScope(state, initialScope);

        const syncVisibleScope = () => {
            const scope = activeScope(state);
            projectConversationTurnScope(state, scope);
            return scope;
        };

        const loadConversation = async (conversationId) => {
            if (state.historyLoading || typeof conversationId !== "string" || !conversationId) {
                return false;
            }
            const previousKey = state.activeTurnScopeKey;
            const previousConversationId = state.conversationId;
            const previousScope = activeScope(state);
            copyVisibleIntoScope(state, previousScope);
            saveDraft(localStorage, previousConversationId, state.draft);

            const key = conversationScopeKey(conversationId);
            state.activeTurnScopeKey = key;
            state.conversationId = conversationId;
            const targetScope = ensureScope(state, key, conversationId);
            projectConversationTurnScope(state, targetScope);

            const loaded = await loadChatHistory({
                state,
                rpcCall: rpc,
                conversationId,
            });
            if (!loaded) {
                state.activeTurnScopeKey = previousKey;
                state.conversationId = previousConversationId;
                projectConversationTurnScope(state, previousScope);
                return false;
            }
            decorateConversationRuntime(state);
            targetScope.messages = [...state.messages];
            targetScope.conversationId = state.conversationId;
            state.draft = loadDraft(localStorage, conversationId);
            projectConversationTurnScope(state, targetScope);
            state.historyView = false;
            saveRecentActiveChat(sessionStorage, conversationId);
            return true;
        };

        const startNewConversation = () => {
            if (state.historyLoading) {
                return false;
            }
            const previousScope = activeScope(state);
            copyVisibleIntoScope(state, previousScope);
            saveDraft(localStorage, state.conversationId, state.draft);
            clearRecentActiveChat(sessionStorage);
            resetForNewConversation(state, localStorage);
            state.activeTurnScopeKey = nextNewScopeKey(state);
            const scope = ensureScope(state, state.activeTurnScopeKey, null);
            projectConversationTurnScope(state, scope);
            state.draft = loadDraft(localStorage, null);
            state.historyView = false;
            return true;
        };

        service.loadHistory = async (conversationId = state.conversationId) => {
            if (state.runtimeState !== "authenticated") {
                return false;
            }
            if (conversationId) {
                return loadConversation(conversationId);
            }
            const loaded = await loadChatHistory({ state, rpcCall: rpc, conversationId: null });
            if (loaded) {
                decorateConversationRuntime(state);
                state.historyView = true;
            }
            return loaded;
        };

        service.newConversation = () => {
            if (state.runtimeState !== "authenticated") {
                return false;
            }
            return startNewConversation();
        };

        service.selectConversation = async (conversationId) => {
            if (state.runtimeState !== "authenticated") {
                return false;
            }
            return loadConversation(conversationId);
        };

        service.showHistory = async () => {
            if (state.historyLoading) {
                return false;
            }
            const scope = activeScope(state);
            copyVisibleIntoScope(state, scope);
            saveDraft(localStorage, state.conversationId, state.draft);
            clearRecentActiveChat(sessionStorage);
            const loaded = await loadChatHistory({ state, rpcCall: rpc, conversationId: null });
            if (loaded) {
                decorateConversationRuntime(state);
                state.historyView = true;
            }
            return loaded;
        };

        service.submit = async (message) => {
            if (state.runtimeState !== "authenticated") {
                state.errorCode =
                    state.runtimeState === "codex_unavailable"
                        ? "codex_unavailable"
                        : "codex_not_connected";
                return false;
            }
            const scope = activeScope(state);
            copyVisibleIntoScope(state, scope);
            const draftConversationId = scope.conversationId;
            const sent = await submitScopedTurn({
                state,
                screenContext: dependencies.odoo_ai_screen_context,
                scope,
                message,
            });
            if (sent) {
                state.historyView = false;
                saveRecentActiveChat(sessionStorage, scope.conversationId);
                if (state.activeTurnScopeKey === scope.key) {
                    state.draft = "";
                }
                saveDraft(localStorage, draftConversationId, "");
                saveDraft(localStorage, scope.conversationId, "");
            }
            if (
                !sent &&
                ["authentication_failed", "codex_not_connected", "codex_unavailable"].includes(
                    scope.errorCode
                ) &&
                typeof baseRefreshRuntimeAccount === "function"
            ) {
                await baseRefreshRuntimeAccount();
            }
            return sent;
        };

        service.decide = async (decision) => {
            const scope = activeScope(state);
            copyVisibleIntoScope(state, scope);
            if (scope.loading || scope.decisionLoading || recoveryPending(scope)) {
                return false;
            }
            if (state.activeTurnScopeKey === scope.key) {
                state.decisionLoading = true;
            }
            try {
                const decided = await submitActionDecision({
                    state: scope,
                    rpcCall: rpc,
                    decision,
                });
                if (decided) {
                    scope.turnState =
                        scope.result?.plan?.state === "awaiting_confirmation"
                            ? "awaiting_confirmation"
                            : scope.result?.plan?.state === "authorized"
                              ? "running"
                              : "completed";
                    updateConversationList(state, scope);
                }
                return decided;
            } finally {
                scope.decisionLoading = false;
                projectIfActive(state, scope);
            }
        };

        service.retry = async () => {
            const scope = activeScope(state);
            copyVisibleIntoScope(state, scope);
            if (scope.loading || scope.decisionLoading || !recoveryPending(scope)) {
                return false;
            }
            if (state.activeTurnScopeKey === scope.key) {
                state.decisionLoading = true;
            }
            try {
                return await submitActionRetry({ state: scope, rpcCall: rpc });
            } finally {
                scope.decisionLoading = false;
                projectIfActive(state, scope);
            }
        };

        service.retryFailure = async () => {
            const scope = activeScope(state);
            const message = scope.lastSubmittedMessage;
            if (!failureCanRetry(scope.failure) || typeof message !== "string" || !message) {
                return false;
            }
            return service.submit(message);
        };

        service.conversationRuntimeState = (conversationId) => {
            const key = conversationScopeKey(conversationId);
            return key ? conversationRuntimeState(state.turnScopes[key]) : null;
        };
        service.conversationRuntimeLabel = (conversationId) => {
            const key = conversationScopeKey(conversationId);
            return key ? conversationRuntimeLabel(state.turnScopes[key]) : "";
        };

        service.open = () => {
            if (state.runtimeState === "authenticated" && state.chatBootstrapped) {
                state.isOpen = true;
                service.refreshContext();
                syncVisibleScope();
                if (typeof baseRefreshRuntimeAccount === "function") {
                    void baseRefreshRuntimeAccount().then(() => syncVisibleScope());
                }
                return;
            }
            baseOpen();
        };
        service.close = () => {
            const scope = activeScope(state);
            copyVisibleIntoScope(state, scope);
            if (!state.historyView && scope.conversationId) {
                saveRecentActiveChat(sessionStorage, scope.conversationId);
            }
            baseClose();
        };
        service.toggle = () => {
            if (state.isOpen) {
                service.close();
            } else {
                service.open();
            }
        };

        const recentConversationId = loadRecentActiveChat(sessionStorage);
        if (recentConversationId && recentConversationId !== state.conversationId) {
            state.conversationId = recentConversationId;
            state.activeTurnScopeKey = conversationScopeKey(recentConversationId);
            ensureScope(state, state.activeTurnScopeKey, recentConversationId);
        }

        return service;
    },
});
