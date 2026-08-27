import { expect, test } from "@odoo/hoot";
import {
    ACTIVE_CHAT_TTL_MS,
    RECOVERY_PLAN_TTL_MS,
    activeChatStorageKey,
    clearRecentActiveChat,
    clearRecoveryPlanId,
    loadRecentActiveChat,
    loadRecoveryPlanId,
    normalizeRecoveryStatusResponse,
    recoveryPlanStorageKey,
    saveRecentActiveChat,
    saveRecoveryPlanId,
} from "@odoo_ai_assistant/services/assistant_history_service";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

const CONVERSATION_ID = "22345678-1234-4678-9234-567812345678";
const PLAN_ID = "32345678-1234-4678-9234-567812345678";
const SCREEN_CONTEXT = {
    capture() {
        return {
            action_id: null,
            menu_id: null,
            view_type: null,
            model: null,
            res_id: null,
            selected_ids: [],
            allowed_context_subset: {},
            captured_at: "2026-08-24T13:00:00.000Z",
        };
    },
};

function memoryStorage() {
    const values = new Map();
    return {
        getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => values.set(key, value),
        removeItem: (key) => values.delete(key),
    };
}

test("history is the initial view without a recent same-tab conversation", () => {
    clearRecentActiveChat(globalThis.sessionStorage);
    clearRecoveryPlanId(globalThis.localStorage);
    const panel = assistantPanelService.start({}, { odoo_ai_screen_context: SCREEN_CONTEXT });

    expect(panel.state.historyView).toBe(true);
    expect(panel.state.conversationId).toBe(null);

    // The composed panel service intentionally blocks chat actions until the provider account
    // has authenticated. This test exercises the history transition after that bootstrap gate.
    panel.state.runtimeState = "authenticated";
    panel.newConversation();
    expect(panel.state.historyView).toBe(false);
    expect(panel.state.conversationId).toBe(null);
});

test("recent active chat cache is restored only while fresh", () => {
    const storage = memoryStorage();
    const now = 1_000_000;

    expect(saveRecentActiveChat(storage, CONVERSATION_ID, now)).toBe(true);
    expect(loadRecentActiveChat(storage, now + ACTIVE_CHAT_TTL_MS - 1)).toBe(CONVERSATION_ID);
    expect(loadRecentActiveChat(storage, now + ACTIVE_CHAT_TTL_MS + 1)).toBe(null);
    expect(storage.getItem(activeChatStorageKey())).toBe(null);
});

test("a recent conversation in this tab starts as active", () => {
    clearRecentActiveChat(globalThis.sessionStorage);
    clearRecoveryPlanId(globalThis.localStorage);
    saveRecentActiveChat(globalThis.sessionStorage, CONVERSATION_ID);

    const panel = assistantPanelService.start({}, { odoo_ai_screen_context: SCREEN_CONTEXT });

    expect(panel.state.historyView).toBe(false);
    expect(panel.state.conversationId).toBe(CONVERSATION_ID);
    clearRecentActiveChat(globalThis.sessionStorage);
});

test("pending recovery plan cache survives browser sessions while bounded", () => {
    const storage = memoryStorage();
    const now = 2_000_000;

    expect(saveRecoveryPlanId(storage, PLAN_ID, now)).toBe(true);
    expect(loadRecoveryPlanId(storage, now + RECOVERY_PLAN_TTL_MS - 1)).toBe(PLAN_ID);
    expect(loadRecoveryPlanId(storage, now + RECOVERY_PLAN_TTL_MS + 1)).toBe(null);
    expect(storage.getItem(recoveryPlanStorageKey())).toBe(null);
});

test("invalid recovery cache never becomes a plan handle", () => {
    const storage = memoryStorage();
    storage.setItem(
        recoveryPlanStorageKey(),
        JSON.stringify({ version: 1, planId: "not-a-uuid", touchedAt: 2_000_000 })
    );

    expect(loadRecoveryPlanId(storage, 2_000_001)).toBe(null);
    expect(storage.getItem(recoveryPlanStorageKey())).toBe(null);
});

test("in-flight recovery status remains active instead of becoming invalid", () => {
    const normalized = normalizeRecoveryStatusResponse(
        {
            ok: true,
            plan_id: PLAN_ID,
            state: "executing",
            plan: { plan_id: PLAN_ID, state: "executing" },
        },
        PLAN_ID
    );

    expect(normalized.errorCode).toBe(null);
    expect(normalized.receipt.state).toBe("executing");
    expect(normalized.plan.state).toBe("executing");
});

test("recovery status must stay bound to the cached plan id", () => {
    const normalized = normalizeRecoveryStatusResponse(
        {
            ok: true,
            plan_id: "42345678-1234-4678-9234-567812345678",
            state: "executing",
            plan: {
                plan_id: "42345678-1234-4678-9234-567812345678",
                state: "executing",
            },
        },
        PLAN_ID
    );

    expect(normalized.receipt).toBe(null);
    expect(normalized.errorCode).toBe("invalid_response");
});
