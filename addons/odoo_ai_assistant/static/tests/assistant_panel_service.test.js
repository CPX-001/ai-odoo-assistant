import { expect, test } from "@odoo/hoot";
import {
    loadChatHistory,
    loadDraft,
    loadRuntimeStatus,
    normalizeChatResponse,
    normalizeRuntimeStatus,
    recoveryPending,
    resetForNewConversation,
    saveDraft,
    submitActionDecision,
    submitActionRetry,
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
        runtimeLoading: false,
        runtimeState: null,
        runtimeCanConfigure: false,
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

function capabilityStep(state = "previewed") {
    return {
        step_id: "32345678-1234-5678-9234-567812345678:0",
        capability: "odoo.record.patch",
        title: "Cambiar nombre del contacto",
        summary: "patch · AI Test Partner · 1 cambio(s)",
        state,
        risk: "moderate",
        effect_scope: "internal_reversible",
        approval: "policy",
        preview: {
            operation: "patch",
            model: "res.partner",
            record_id: 42,
            display_name: "AI Test Partner",
            changes: [{ field: "name", before: "AI Test Partner", after: "AI Updated Partner" }],
        },
        receipt:
            state === "completed"
                ? {
                      error_code: null,
                      evidence_id: null,
                      outcome: "verified",
                      record_id: 42,
                      record_model: "res.partner",
                  }
                : null,
    };
}

function agentPlan(state = "completed", requiresConfirmation = false, steps = []) {
    return {
        plan_id: "32345678-1234-5678-9234-567812345678",
        state,
        risk: steps.length ? "moderate" : "low",
        metadata: {
            needs_read: !steps.length,
            needs_schema: !steps.length,
            needs_write: Boolean(steps.length),
            needs_business_action: false,
            has_external_effect: false,
            has_irreversible_effect: false,
            is_atomic: true,
            estimated_blast_radius: steps.length,
        },
        policy: {
            confirmation_mode: "risk_based",
            max_auto_risk: "low",
            allow_synthetic_data: false,
            constrained_by: [],
        },
        goal: steps.length ? "Cambiar el nombre" : "Responder con datos efectivos de Odoo",
        assumptions: [],
        steps,
        requires_confirmation: requiresConfirmation,
        expires_at: null,
    };
}

function chatResponse(plan = agentPlan(), answer = "Checked answer") {
    return {
        ok: true,
        workflow: "AGENT",
        turn_id: "12345678-1234-5678-1234-567812345678",
        conversation_id: "22345678-1234-5678-9234-567812345678",
        answer,
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

test("runtime status requires ChatGPT setup until Codex is authenticated", async () => {
    const panelState = state();
    const status = {
        ok: true,
        state: "not_authenticated",
        requires_setup: true,
        can_configure: true,
    };

    expect(normalizeRuntimeStatus(status)).toEqual(status);
    expect(
        await loadRuntimeStatus({ state: panelState, rpcCall: async () => status })
    ).toBe(true);
    expect(panelState.runtimeState).toBe("not_authenticated");
    expect(panelState.runtimeCanConfigure).toBe(true);
});

test("runtime status rejects inconsistent setup flags", () => {
    expect(
        normalizeRuntimeStatus({
            ok: true,
            state: "authenticated",
            requires_setup: true,
            can_configure: true,
        })
    ).toBe(null);
});

test("chat accepts generic capability preview metadata", () => {
    const plan = agentPlan("awaiting_confirmation", true, [capabilityStep()]);
    const normalized = normalizeChatResponse(chatResponse(plan));

    expect(normalized.errorCode).toBe(null);
    expect(normalized.result.plan.steps[0].capability).toBe("odoo.record.patch");
    expect(normalized.result.plan.steps[0].preview.changes[0].after).toBe(
        "AI Updated Partner"
    );
});

test("chat accepts a verified model-scoped receipt for a batch mutation", () => {
    const step = capabilityStep("completed");
    step.capability = "odoo.records.batch_mutate";
    step.preview = {
        operation: "create",
        model: "sale.order",
        count: 2,
        rows: [
            { partner_id: 31, client_order_ref: "TEST-001" },
            { partner_id: 31, client_order_ref: "TEST-002" },
        ],
    };
    step.receipt = {
        error_code: null,
        evidence_id: null,
        outcome: "verified",
        record_id: null,
        record_model: "sale.order",
    };

    const normalized = normalizeChatResponse(chatResponse(agentPlan("completed", false, [step])));

    expect(normalized.errorCode).toBe(null);
    expect(normalized.result.plan.steps[0].receipt.record_id).toBe(null);
    expect(normalized.result.plan.steps[0].receipt.record_model).toBe("sale.order");
});

test("chat sends through the Odoo-native turn queue", async () => {
    const panelState = state();
    const paths = [];

    const executed = await submitAssistantRequest({
        state: panelState,
        screenContext: { capture: () => SCREEN },
        waitCall: async () => {},
        rpcCall: async (path) => {
            paths.push(path);
            if (path === "/odoo_ai/v1/turn") {
                return {
                    ok: true,
                    turn_id: "12345678-1234-5678-1234-567812345678",
                    state: "queued",
                };
            }
            return {
                ok: true,
                turn_id: "12345678-1234-5678-1234-567812345678",
                state: "completed",
                response: chatResponse(),
            };
        },
        message: "Explícame el backend",
    });

    expect(executed).toBe(true);
    expect(paths).toEqual(["/odoo_ai/v1/turn", "/odoo_ai/v1/turn/status"]);
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
        active_turn: null,
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
        waitCall: async () => {},
        message: "Pregunta",
    };

    const first = submitAssistantRequest(options);
    const second = await submitAssistantRequest(options);
    expect(second).toBe(false);
    expect(calls).toBe(1);
    resolveRpc({
        ok: true,
        turn_id: "12345678-1234-5678-1234-567812345678",
        state: "completed",
        response: chatResponse(),
    });
    await first;
    expect(panelState.loading).toBe(false);
});

test("approve uses native plan decision then status until verified completion", async () => {
    const panelState = state();
    const awaiting = agentPlan("awaiting_confirmation", true, [capabilityStep()]);
    panelState.result = chatResponse(awaiting, "He preparado el cambio.");
    const paths = [];

    const approved = await submitActionDecision({
        state: panelState,
        decision: "approve",
        waitCall: async () => {},
        rpcCall: async (path) => {
            paths.push(path);
            if (path === "/odoo_ai/v1/turn/plan-decision") {
                return {
                    ok: true,
                    plan_id: awaiting.plan_id,
                    state: "authorized",
                    plan: agentPlan("authorized", true, [capabilityStep()]),
                    response: null,
                };
            }
            const completed = agentPlan("completed", true, [capabilityStep("completed")]);
            return {
                ok: true,
                plan_id: awaiting.plan_id,
                state: "completed",
                turn_state: "completed",
                plan: completed,
                response: chatResponse(completed, "He completado y verificado la acción."),
                error_code: null,
            };
        },
    });

    expect(approved).toBe(true);
    expect(paths).toEqual([
        "/odoo_ai/v1/turn/plan-decision",
        "/odoo_ai/v1/turn/plan-status",
    ]);
    expect(panelState.result.plan.state).toBe("completed");
    expect(panelState.actionReceipt.state).toBe("completed");
    expect(recoveryPending(panelState)).toBe(false);
});

test("reject is terminal and never polls or executes", async () => {
    const panelState = state();
    const awaiting = agentPlan("awaiting_confirmation", true, [capabilityStep()]);
    panelState.result = chatResponse(awaiting, "He preparado el cambio.");
    const paths = [];
    const rejected = agentPlan("rejected", true, [capabilityStep()]);

    const result = await submitActionDecision({
        state: panelState,
        decision: "reject",
        rpcCall: async (path) => {
            paths.push(path);
            return {
                ok: true,
                plan_id: awaiting.plan_id,
                state: "rejected",
                plan: rejected,
                response: chatResponse(
                    rejected,
                    "Acción cancelada. No se ha realizado ningún cambio."
                ),
            };
        },
    });

    expect(result).toBe(true);
    expect(paths).toEqual(["/odoo_ai/v1/turn/plan-decision"]);
    expect(panelState.result.plan.state).toBe("rejected");
    expect(panelState.result.answer).toBe("Acción cancelada. No se ha realizado ningún cambio.");
});

test("recovery control is status-only and never re-executes the action", async () => {
    const panelState = state();
    const authorized = agentPlan("authorized", true, [capabilityStep()]);
    panelState.result = chatResponse(authorized);
    panelState.actionReceipt = {
        ok: true,
        plan_id: authorized.plan_id,
        state: "recovery_required",
        plan: authorized,
        response: null,
    };
    const paths = [];

    expect(recoveryPending(panelState)).toBe(true);
    const checked = await submitActionRetry({
        state: panelState,
        waitCall: async () => {},
        rpcCall: async (path) => {
            paths.push(path);
            return {
                ok: true,
                plan_id: authorized.plan_id,
                state: "authorized",
                turn_state: "recovery_required",
                plan: authorized,
                response: null,
                error_code: "worker_lost_after_write_barrier",
            };
        },
    });

    expect(checked).toBe(true);
    expect(paths).toEqual(["/odoo_ai/v1/turn/plan-status"]);
    expect(panelState.actionReceipt.state).toBe("recovery_required");
    expect(panelState.errorCode).toBe("worker_lost_after_write_barrier");
});
