/** @odoo-module **/

import {
    assistantPanelService,
    normalizeChatResponse,
    recoveryPending,
    saveDraft,
} from "@odoo_ai_assistant/services/assistant_panel_service";
import { streamAssistantChat } from "@odoo_ai_assistant/services/assistant_stream_client";

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

export async function submitStreamingAssistantRequest({
    state,
    screenContext,
    message,
    streamCall = streamAssistantChat,
}) {
    if (state.loading || state.decisionLoading || recoveryPending(state)) {
        return false;
    }
    const normalized = typeof message === "string" ? message.trim() : "";
    if (!normalized || normalized.length > 4000) {
        state.errorCode = "invalid_context";
        return false;
    }

    state.context = screenContext.capture();
    state.loading = true;
    state.streamingText = "";
    state.errorCode = null;
    state.actionReceipt = null;
    const previousConversationId = state.conversationId;
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

    try {
        const response = await streamCall({
            payload: {
                message: normalized,
                screen: state.context,
                conversation_id: state.conversationId,
            },
            onDelta: async (text) => {
                if (typeof text !== "string" || !text) {
                    throw new Error("invalid_stream");
                }
                const next = `${state.streamingText || ""}${text}`;
                if (next.length > 16384) {
                    throw new Error("invalid_stream");
                }
                state.streamingText = next;
            },
        });
        const parsed = normalizeChatResponse(response);
        state.streamingText = "";
        state.result = parsed.result;
        state.errorCode = parsed.errorCode;
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
    } catch {
        state.streamingText = "";
        state.result = null;
        state.errorCode = "service_unavailable";
        return false;
    } finally {
        state.loading = false;
    }
}

const originalStart = assistantPanelService.start;
assistantPanelService.start = function (env, dependencies) {
    const service = originalStart.call(this, env, dependencies);
    const state = service.state;
    state.streamingText = "";
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
    return service;
};
