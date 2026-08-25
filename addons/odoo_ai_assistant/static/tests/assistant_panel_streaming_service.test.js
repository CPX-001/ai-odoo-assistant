import { expect, test } from "@odoo/hoot";
import { submitStreamingAssistantRequest } from "@odoo_ai_assistant/services/assistant_panel_streaming_service";

const SCREEN = {
    action_id: null,
    menu_id: null,
    view_type: "list",
    model: "project.task",
    res_id: null,
    selected_ids: [],
    allowed_context_subset: {},
    captured_at: "2026-08-25T16:00:00.000Z",
};

function state() {
    return {
        context: null,
        errorCode: null,
        loading: false,
        historyLoading: false,
        decisionLoading: false,
        policyLoading: false,
        streamingText: "",
        result: null,
        actionReceipt: null,
        conversationId: null,
        conversations: [],
        messages: [],
        draft: "",
    };
}

function plan(planState = "completed") {
    return {
        plan_id: "32345678-1234-5678-9234-567812345678",
        state: planState,
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
        goal: planState === "failed" ? "Explicar el fallo" : "Responder",
        assumptions: [],
        steps: [],
        requires_confirmation: false,
        expires_at: null,
    };
}

function response(answer = "Respuesta final", planState = "completed") {
    return {
        ok: true,
        workflow: "AGENT",
        turn_id: "12345678-1234-5678-1234-567812345678",
        conversation_id: "22345678-1234-5678-9234-567812345678",
        answer,
        confidence: planState === "failed" ? "low" : "high",
        limitations: [],
        citations: [],
        plan: plan(planState),
    };
}

test("panel shows the user immediately and accumulates provisional assistant text", async () => {
    const panelState = state();
    const observedStreaming = [];

    const sent = await submitStreamingAssistantRequest({
        state: panelState,
        screenContext: { capture: () => SCREEN },
        message: "Lista todos los presupuestos",
        streamCall: async ({ payload, onDelta }) => {
            expect(payload.screen.model).toBe("project.task");
            expect(panelState.messages).toHaveLength(1);
            expect(panelState.messages[0].role).toBe("user");
            expect(panelState.loading).toBe(true);
            await onDelta("Hay ");
            observedStreaming.push(panelState.streamingText);
            await onDelta("cinco presupuestos.");
            observedStreaming.push(panelState.streamingText);
            return response("Hay cinco presupuestos.");
        },
    });

    expect(sent).toBe(true);
    expect(observedStreaming).toEqual(["Hay ", "Hay cinco presupuestos."]);
    expect(panelState.streamingText).toBe("");
    expect(panelState.loading).toBe(false);
    expect(panelState.errorCode).toBe(null);
    expect(panelState.messages).toHaveLength(2);
    expect(panelState.messages[1].role).toBe("assistant");
    expect(panelState.messages[1].content).toBe("Hay cinco presupuestos.");
    expect(panelState.conversationId).toBe("22345678-1234-5678-9234-567812345678");
});

test("a conversational failed final replaces provisional text without a technical error", async () => {
    const panelState = state();

    const sent = await submitStreamingAssistantRequest({
        state: panelState,
        screenContext: { capture: () => SCREEN },
        message: "Elimínalos todos",
        streamCall: async ({ onDelta }) => {
            await onDelta("Voy a comprobar...");
            return response(
                "No he podido completar la operación y no se ha aplicado ningún cambio.",
                "failed"
            );
        },
    });

    expect(sent).toBe(true);
    expect(panelState.streamingText).toBe("");
    expect(panelState.errorCode).toBe(null);
    expect(panelState.result.plan.state).toBe("failed");
    expect(panelState.messages[1].content).toInclude("no se ha aplicado ningún cambio");
});

test("a broken browser stream discards provisional text and keeps a plain fallback path", async () => {
    const panelState = state();

    const sent = await submitStreamingAssistantRequest({
        state: panelState,
        screenContext: { capture: () => SCREEN },
        message: "Elimínalos todos",
        streamCall: async ({ onDelta }) => {
            await onDelta("Texto provisional que no debe quedar como final");
            throw new Error("connection_lost");
        },
    });

    expect(sent).toBe(false);
    expect(panelState.streamingText).toBe("");
    expect(panelState.result).toBe(null);
    expect(panelState.errorCode).toBe("service_unavailable");
    expect(panelState.messages).toHaveLength(1);
    expect(panelState.messages[0].role).toBe("user");
});

test("streaming guard prevents a second simultaneous turn", async () => {
    const panelState = state();
    let release;
    let calls = 0;
    const streamCall = () => {
        calls += 1;
        return new Promise((resolve) => {
            release = resolve;
        });
    };
    const options = {
        state: panelState,
        screenContext: { capture: () => SCREEN },
        message: "Pregunta",
        streamCall,
    };

    const first = submitStreamingAssistantRequest(options);
    const second = await submitStreamingAssistantRequest(options);

    expect(second).toBe(false);
    expect(calls).toBe(1);
    release(response());
    await first;
    expect(panelState.loading).toBe(false);
});
