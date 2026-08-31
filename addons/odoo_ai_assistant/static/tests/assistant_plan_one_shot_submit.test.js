import { expect, test } from "@odoo/hoot";
import { submitStreamingAssistantRequest } from "@odoo_ai_assistant/services/assistant_panel_streaming_service";

function state() {
    return {
        loading: false,
        decisionLoading: false,
        actionReceipt: null,
        result: null,
        failure: null,
        errorCode: null,
        context: null,
        streamingText: "",
        activityEvents: [],
        currentActivity: null,
        lastSubmittedMessage: "",
        conversationId: null,
        conversations: [],
        messages: [],
        planningMode: "deliberate",
    };
}

const screenContext = { capture: () => ({ model: null, res_id: null }) };

test("one-shot Plan is consumed when Odoo durably accepts the turn", async () => {
    const current = state();
    const sent = await submitStreamingAssistantRequest({
        state: current,
        screenContext,
        message: "Planifica esta petición",
        streamCall: async ({ payload, onTiming }) => {
            expect(payload.planning_mode).toBe("deliberate");
            await onTiming({ point: "turn_persisted", turn_id: "turn-plan-1", elapsed_ms: 5 });
            throw new Error("stream disconnected after durable submit");
        },
    });

    expect(sent).toBe(false);
    expect(current.planningMode).toBe("adaptive");
});


test("Plan remains selected when submission fails before a durable turn exists", async () => {
    const current = state();
    const sent = await submitStreamingAssistantRequest({
        state: current,
        screenContext,
        message: "Planifica esta petición",
        streamCall: async ({ payload }) => {
            expect(payload.planning_mode).toBe("deliberate");
            throw new Error("submit failed before persistence");
        },
    });

    expect(sent).toBe(false);
    expect(current.planningMode).toBe("deliberate");
});
