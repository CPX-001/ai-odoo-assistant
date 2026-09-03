/** @odoo-module **/

import {
    assistantPanelService,
    normalizeChatResponse,
    recoveryPending,
    saveDraft,
} from "@odoo_ai_assistant/services/assistant_panel_service";
import {
    failureCanRetry,
    failureFromError,
} from "@odoo_ai_assistant/services/assistant_failure_contract";
import { streamAssistantChatLive } from "@odoo_ai_assistant/services/assistant_live_stream_client";
import { createAnswerStreamPresenter } from "@odoo_ai_assistant/services/assistant_answer_stream_presenter";

const MAX_ACTIVITY_EVENTS = 1024;
let pendingMessageSequence = 0;

function storage() {
    try {
        return globalThis.localStorage || null;
    } catch {
        return null;
    }
}

function pendingMessageId() {
    pendingMessageSequence += 1;
    return `local-user-pending-${Date.now()}-${pendingMessageSequence}`;
}

function updateConversationList(state, normalizedMessage, previousConversationId) {
    if (
        state.conversationId &&
        !state.conversations.some((item) => item.conversation_id === state.conversationId)
    ) {
        const now = new Date().toISOString();
        state.conversations = [
            {
                conversation_id: state.conversationId,
                title: normalizedMessage.slice(0, 160),
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
}

function appendActivity(state, event) {
    if (!event || !Number.isSafeInteger(event.sequence)) {
        throw new Error("invalid_stream");
    }
    const existing = state.activityEvents || [];
    if (existing.some((item) => item.sequence === event.sequence)) {
        return;
    }
    const next = [...existing, event].slice(-MAX_ACTIVITY_EVENTS);
    state.activityEvents = next;
    state.currentActivity = event;
}

export async function submitStreamingAssistantRequest({
    state,
    screenContext,
    message,
    streamCall = streamAssistantChatLive,
    presenterFactory = createAnswerStreamPresenter,
}) {
    if (state.loading || state.decisionLoading || recoveryPending(state)) {
        return false;
    }
    const normalized = typeof message === "string" ? message.trim() : "";
    if (!normalized || normalized.length > 4000) {
        state.failure = null;
        state.errorCode = "invalid_context";
        return false;
    }

    state.context = screenContext.capture();
    state.loading = true;
    state.streamingText = "";
    state.activityEvents = [];
    state.currentActivity = null;
    state.errorCode = null;
    state.failure = null;
    state.actionReceipt = null;
    state.actionStatusConnectionInterrupted = false;
    state.lastSubmittedMessage = normalized;
    const previousConversationId = state.conversationId;
    const submittedPlanningMode = state.planningMode === "deliberate" ? "deliberate" : "adaptive";
    state.taskPlanRequested = submittedPlanningMode === "deliberate";
    const submittedAt = new Date().toISOString();
    state.messages = [
        ...state.messages,
        {
            message_id: pendingMessageId(),
            role: "user",
            content: normalized,
            created_at: submittedAt,
        },
    ];
    const presenter = presenterFactory({
        writeText: (text) => {
            state.streamingText = text;
        },
    });

    try {
        const response = await streamCall({
            payload: {
                message: normalized,
                screen: state.context,
                conversation_id: state.conversationId,
                planning_mode: submittedPlanningMode,
            },
            onActivity: async (event) => appendActivity(state, event),
            onDelta: async (text) => {
                presenter.push(text);
            },
            onTiming: async (timing) => {
                if (
                    timing?.point === "turn_persisted" &&
                    submittedPlanningMode === "deliberate" &&
                    state.planningMode === "deliberate"
                ) {
                    state.planningMode = "adaptive";
                }
            },
        });
        const parsed = normalizeChatResponse(response);
        if (parsed.result) {
            await presenter.reconcile(parsed.result.answer);
        }
        presenter.stop();
        state.streamingText = "";
        state.result = parsed.result;
        state.errorCode = parsed.errorCode;
        state.failure = null;
        if (!parsed.result) {
            return false;
        }

        state.conversationId = parsed.result.conversation_id || state.conversationId;
        updateConversationList(state, normalized, previousConversationId);
        state.messages = [
            ...state.messages,
            {
                message_id: `local-assistant-${parsed.result.turn_id}`,
                role: "assistant",
                content: parsed.result.answer,
                created_at: new Date().toISOString(),
            },
        ];
        return true;
    } catch (error) {
        presenter.stop();
        const parsed = failureFromError(error);
        state.streamingText = "";
        state.result = null;
        state.errorCode = parsed.code;
        state.failure = parsed.failure;
        return false;
    } finally {
        presenter.stop();
        state.loading = false;
    }
}

const originalStart = assistantPanelService.start;
assistantPanelService.start = function (env, dependencies) {
    const service = originalStart.call(this, env, dependencies);
    const state = service.state;
    state.streamingText = "";
    state.activityEvents = [];
    state.currentActivity = null;
    state.failure = null;
    state.lastSubmittedMessage = "";
    service.submit = async (message) => {
        const draftConversationId = state.conversationId;
        const sent = await submitStreamingAssistantRequest({
            state,
            screenContext: dependencies.odoo_ai_screen_context,
            message,
        });
        if (sent) {
            state.draft = "";
            const browserStorage = storage();
            saveDraft(browserStorage, draftConversationId, "");
            saveDraft(browserStorage, state.conversationId, "");
        }
        return sent;
    };
    const originalNewConversation = service.newConversation.bind(service);
    service.newConversation = () => {
        const changed = originalNewConversation();
        if (changed) {
            state.activityEvents = [];
            state.currentActivity = null;
            state.streamingText = "";
        }
        return changed;
    };
    const originalSelectConversation = service.selectConversation.bind(service);
    service.selectConversation = async (conversationId) => {
        const changed = await originalSelectConversation(conversationId);
        if (changed) {
            state.activityEvents = [];
            state.currentActivity = null;
            state.streamingText = "";
        }
        return changed;
    };
    service.retryFailure = async () => {
        const message = state.lastSubmittedMessage;
        if (!failureCanRetry(state.failure) || typeof message !== "string" || !message) {
            return false;
        }
        return service.submit(message);
    };
    return service;
};
