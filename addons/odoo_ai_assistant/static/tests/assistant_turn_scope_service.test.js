import { expect, test } from "@odoo/hoot";
import {
    bindConversationTurnScope,
    conversationRuntimeLabel,
    conversationRuntimeState,
    conversationScopeKey,
    createConversationTurnScope,
    normalizeSubmittedMessages,
    normalizeVisibleAttachments,
    projectConversationTurnScope,
    refreshTurnScopeModelPreferences,
    submitScopedTurn,
} from "@odoo_ai_assistant/services/zzz_assistant_turn_scope_service";

test("transport-only attachment markers never enter the optimistic user projection", () => {
    const marker = "[[odoo_ai_attachment:0123456789abcdef0123456789abcdef]]";
    expect(
        normalizeSubmittedMessages(`Añade este archivo.\n${marker}`, "Añade este archivo.")
    ).toEqual({
        transport: `Añade este archivo.\n${marker}`,
        visible: "Añade este archivo.",
    });
});

test("visible attachment metadata is bounded and does not expose transport tokens", () => {
    expect(
        normalizeVisibleAttachments([
            { name: "  manual.pdf  ", mimetype: "application/pdf", size: 1234 },
            { name: "", token: "secret-transport-token" },
        ])
    ).toEqual([{ name: "manual.pdf", mimetype: "application/pdf", size: 1234 }]);
});

function scopedState() {
    return {
        turnScopes: {},
        activeTurnScopeKey: "new:1",
        conversationId: null,
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

test("active conversation projects only its own busy state", () => {
    const state = scopedState();
    const running = createConversationTurnScope({
        key: conversationScopeKey("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        conversationId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    });
    running.loading = true;
    running.turnState = "running";
    running.streamingText = "Respuesta parcial de A";
    const idle = createConversationTurnScope({
        key: conversationScopeKey("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        conversationId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    });
    state.turnScopes[running.key] = running;
    state.turnScopes[idle.key] = idle;

    state.activeTurnScopeKey = idle.key;
    projectConversationTurnScope(state, idle);

    expect(state.loading).toBe(false);
    expect(state.streamingText).toBe("");
    expect(running.loading).toBe(true);
    expect(running.streamingText).toBe("Respuesta parcial de A");
});

test("returning to a running chat restores its live UI projection", () => {
    const state = scopedState();
    const scope = createConversationTurnScope({
        key: conversationScopeKey("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        conversationId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    });
    scope.loading = true;
    scope.turnState = "running";
    scope.streamingText = "Parcial";
    scope.activityEvents = [{ sequence: 1, label: "Consultando Odoo" }];
    scope.currentActivity = scope.activityEvents[0];
    state.turnScopes[scope.key] = scope;
    state.activeTurnScopeKey = scope.key;

    projectConversationTurnScope(state, scope);

    expect(state.loading).toBe(true);
    expect(state.streamingText).toBe("Parcial");
    expect(state.currentActivity.label).toBe("Consultando Odoo");
});

test("temporary new-chat scope binds to the durable conversation and turn", () => {
    const state = scopedState();
    const scope = createConversationTurnScope({ key: "new:1" });
    state.turnScopes[scope.key] = scope;

    bindConversationTurnScope(state, scope, {
        conversationId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        turnId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        turnState: "queued",
    });

    const key = conversationScopeKey("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    expect(state.activeTurnScopeKey).toBe(key);
    expect(state.conversationId).toBe("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    expect(state.turnScopes["new:1"]).toBe(undefined);
    expect(state.turnScopes[key].turnId).toBe("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
});

test("conversation runtime state stays compact and product-facing", () => {
    const scope = createConversationTurnScope({ key: "new:1" });
    scope.loading = true;
    scope.turnState = "queued";
    expect(conversationRuntimeState(scope)).toBe("queued");
    expect(conversationRuntimeLabel(scope)).toBe("En cola");

    scope.turnState = "running";
    expect(conversationRuntimeState(scope)).toBe("running");

    scope.loading = false;
    scope.turnState = "awaiting_confirmation";
    expect(conversationRuntimeState(scope)).toBe("awaiting_approval");

    scope.turnState = "recovery_required";
    expect(conversationRuntimeState(scope)).toBe("recovery");

    scope.turnState = "failed";
    scope.errorCode = "engine_timeout";
    expect(conversationRuntimeState(scope)).toBe("failed");

    scope.result = { plan: { state: "executing" } };
    expect(conversationRuntimeState(scope)).toBe("failed");

    scope.errorCode = null;
    scope.turnState = "completed";
    expect(conversationRuntimeState(scope)).toBe("completed");
});

test("ordinary approved execution is not mislabeled as recovery", () => {
    const scope = createConversationTurnScope({ key: "new:1" });
    scope.turnState = "running";
    scope.result = { plan: { state: "authorized" } };
    expect(conversationRuntimeState(scope)).toBe("queued");

    scope.result = { plan: { state: "executing" } };
    expect(conversationRuntimeState(scope)).toBe("running");

    scope.turnState = "recovery_required";
    expect(conversationRuntimeState(scope)).toBe("recovery");
});

test("turn-scoped submit forwards Direct mode and suppresses TaskPlan presentation", async () => {
    const state = scopedState();
    state.planningMode = "adaptive";
    const scope = createConversationTurnScope({ key: "new:1" });
    state.turnScopes[scope.key] = scope;
    let submittedPayload;

    const sent = await submitScopedTurn({
        state,
        scope,
        screenContext: { capture: () => ({ model: null, res_id: null }) },
        message: "Elimina los contactos restantes",
        displayMessage: null,
        displayAttachments: [],
        onConversationBound: () => {},
        streamCall: async ({ payload }) => {
            submittedPayload = payload;
            throw new Error("stop after inspecting payload");
        },
    });

    expect(sent).toBe(false);
    expect(submittedPayload.planning_mode).toBe("adaptive");
    expect(scope.taskPlanRequested).toBe(false);
});

test("turn-scoped submit preserves explicit Plan as a one-turn presentation choice", async () => {
    const state = scopedState();
    state.planningMode = "deliberate";
    const scope = createConversationTurnScope({ key: "new:1" });
    state.turnScopes[scope.key] = scope;
    let submittedPayload;

    await submitScopedTurn({
        state,
        scope,
        screenContext: { capture: () => ({ model: null, res_id: null }) },
        message: "Planifica el cierre trimestral",
        displayMessage: null,
        displayAttachments: [],
        onConversationBound: () => {},
        streamCall: async ({ payload }) => {
            submittedPayload = payload;
            throw new Error("stop after inspecting payload");
        },
    });

    expect(submittedPayload.planning_mode).toBe("deliberate");
    expect(scope.taskPlanRequested).toBe(true);
});

test("reopening a scoped chat preserves the model-catalog refresh hook", async () => {
    let calls = 0;
    const loaded = await refreshTurnScopeModelPreferences({
        loadModelPreferences() {
            calls += 1;
            return true;
        },
    });

    expect(loaded).toBe(true);
    expect(calls).toBe(1);
    expect(await refreshTurnScopeModelPreferences({})).toBe(false);
});
