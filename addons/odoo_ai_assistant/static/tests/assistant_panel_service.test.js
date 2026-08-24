import { expect, test } from "@odoo/hoot";
import {
    loadChatHistory,
    loadDraft,
    normalizeChatResponse,
    resetForNewConversation,
    saveDraft,
    submitActionDecision,
    submitAssistantRequest,
} from "@odoo_ai_assistant/services/assistant_panel_service";

const SCREEN = {
    action_id: null,
    menu_id: null,
    view_type: null,
    model: null,
    res_id: null,
    selected_ids: [],
    allowed_context_subset: {},
    captured_at: "2026-08-24T08:30:00.000Z",
};

function state() {
    return {
        context: null,
        errorCode: null,
        loading: false,
        historyLoading: false,
        decisionLoading: false,
        policyLoading: false,
        result: null,
        actionReceipt: null,
        agentPolicy: {
            confirmation_mode: "risk_based",
            max_auto_risk: "low",
        },
        conversationId: null,
        conversations: [],
        messages: [],
        draft: "",
    };
}

function agentPlan(state = "completed", requiresConfirmation = false) {
    return {
        plan_id: "32345678-1234-5678-9234-567812345678",
        state,
        risk: "low",
        metadata: {
            needs_read: true,
            needs_schema: true,
            needs_write: false,
            needs_business_action: false,
            has_external_effect: false,
            has_irreversible_effect: false,
            is_atomic: true,
            estimated_blast_radius: 0,
        },
        policy: {
            confirmation_mode: "risk_based",
            max_auto_risk: "low",
            allow_synthetic_data: false,
            constrained_by: ["system_ceiling"],
        },
        goal: "Responder con datos efectivos de Odoo",
        assumptions: [],
        steps: [],
        requires_confirmation: requiresConfirmation,
        expires_at: "2026-08-24T08:35:00Z",
    };
}

function chatResponse(plan = agentPlan()) {
    return {
        ok: true,
        workflow: "AGENT",
        turn_id: "12345678-1234-5678-1234-567812345678",
        conversation_id: "22345678-1234-5678-9234-567812345678",
        answer: "Checked answer",
        confidence: "high",
        limitations: [],
        citations: [],
        plan,
    };
}

test("chat accepts a unified-agent response without exposing a category selector", () => {
    const normalized = normalizeChatResponse(chatResponse());
    expect(normalized.errorCode).toBe(null);
    expect(normalized.result.answer).toBe("Checked answer");
    expect(normalized.result.workflow).toBe("AGENT");
    expect(normalized.result.plan.state).toBe("completed");
});

test("chat sends no workflow and works without an active model", async () => {
    const panelState = state();
    let observedPath;
    let observedPayload;

    const executed = await submitAssistantRequest({
        state: panelState,
        screenContext: { capture: () => SCREEN },
        rpcCall: async (path, payload) => {
            observedPath = path;
            observedPayload = payload;
            return chatResponse();
        },
        message: "Explícame el backend",
    });

    expect(executed).toBe(true);
    expect(observedPath).toBe("/odoo_ai/v1/chat");
    expect(observedPayload.workflow).toBe(undefined);
    expect(observedPayload.screen.model).toBe(null);
    expect(panelState.conversationId).toBe("22345678-1234-5678-9234-567812345678");
});

test("draft survives save and reload per conversation", () => {
    const values = new Map();
    const storage = {
        getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => values.set(key, value),
    };
    const conversationId = "22345678-1234-5678-9234-567812345678";

    expect(saveDraft(storage, conversationId, "texto sin enviar")).toBe(true);
    expect(loadDraft(storage, conversationId)).toBe("texto sin enviar");
    expect(loadDraft(storage, null)).toBe("");
});

test("new conversation clears the composer and its new-chat draft", () => {
    const values = new Map();
    const storage = {
        getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => values.set(key, value),
    };
    const panelState = state();
    panelState.conversationId = "22345678-1234-5678-9234-567812345678";
    panelState.draft = "texto pendiente";
    panelState.messages = [{ role: "user", content: "anterior" }];
    saveDraft(storage, null, "borrador antiguo de chat nuevo");

    resetForNewConversation(panelState, storage);

    expect(panelState.conversationId).toBe(null);
    expect(panelState.messages).toEqual([]);
    expect(panelState.draft).toBe("");
    expect(loadDraft(storage, null)).toBe("");
    expect(loadDraft(storage, "22345678-1234-5678-9234-567812345678")).toBe(
        "texto pendiente"
    );
});

test("history hydrates conversations and messages", async () => {
    const panelState = state();
    const response = {
        ok: true,
        active_conversation_id: "22345678-1234-5678-9234-567812345678",
        conversations: [
            {
                conversation_id: "22345678-1234-5678-9234-567812345678",
                title: "Facturas vencidas",
                created_at: "2026-08-24T08:00:00Z",
                updated_at: "2026-08-24T08:30:00Z",
            },
        ],
        messages: [
            {
                message_id: "32345678-1234-5678-9234-567812345678",
                role: "user",
                content: "¿Qué facturas están vencidas?",
                created_at: "2026-08-24T08:30:00Z",
            },
        ],
    };

    const loaded = await loadChatHistory({
        state: panelState,
        rpcCall: async () => response,
    });

    expect(loaded).toBe(true);
    expect(panelState.conversations).toHaveLength(1);
    expect(panelState.messages[0].role).toBe("user");
});

test("loading guard prevents simultaneous chat turns", async () => {
    const panelState = state();
    let resolveRpc;
    let calls = 0;
    const rpcCall = () => {
        calls += 1;
        return new Promise((resolve) => {
            resolveRpc = resolve;
        });
    };
    const options = {
        state: panelState,
        screenContext: { capture: () => SCREEN },
        rpcCall,
        message: "Pregunta",
    };

    const first = submitAssistantRequest(options);
    const second = await submitAssistantRequest(options);
    expect(second).toBe(false);
    expect(calls).toBe(1);
    resolveRpc(chatResponse());
    await first;
    expect(panelState.loading).toBe(false);
});

test("action decision remains explicit and one-shot from the UI", async () => {
    const panelState = state();
    panelState.result = chatResponse(agentPlan("awaiting_confirmation", true));
    let resolveRpc;
    let calls = 0;
    const rpcCall = () => {
        calls += 1;
        return new Promise((resolve) => {
            resolveRpc = resolve;
        });
    };

    const first = submitActionDecision({ state: panelState, rpcCall, decision: "approve" });
    const second = await submitActionDecision({ state: panelState, rpcCall, decision: "approve" });
    expect(second).toBe(false);
    expect(calls).toBe(1);
    resolveRpc({
        ok: true,
        plan_id: panelState.result.plan.plan_id,
        state: "completed",
        plan: agentPlan("completed", false),
    });
    await first;
    expect(panelState.actionReceipt.state).toBe("completed");
    expect(panelState.result.plan.state).toBe("completed");
});
