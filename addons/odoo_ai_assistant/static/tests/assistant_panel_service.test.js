import { expect, test } from "@odoo/hoot";
import {
    normalizeWorkflowResponse,
    submitAssistantRequest,
    submitExplainRequest,
} from "@odoo_ai_assistant/services/assistant_panel_service";

const SCREEN = {
    model: "sale.order",
    res_id: 42,
    captured_at: "2026-08-22T10:30:00.000Z",
};

function state(workflow = "EXPLAIN") {
    return {
        context: null,
        errorCode: null,
        loading: false,
        result: null,
        workflow,
    };
}

function response(workflow, citations = []) {
    return {
        ok: true,
        workflow,
        turn_id: "12345678-1234-5678-1234-567812345678",
        answer: "Checked answer",
        confidence: "high",
        limitations: [],
        citations,
    };
}

test("adversarial answer and citation labels remain plain response data", () => {
    const answer =
        '<script>globalThis.pwned = true</script><a href="javascript:alert(1)">x</a>';
    const value = response("HOW_TO", [
        {
            evidence_id: "12345678-1234-5678-1234-567812345678",
            kind: "navigation",
            path: ["<img src=x onerror=globalThis.pwned=true>"],
        },
    ]);
    value.answer = answer;

    const normalized = normalizeWorkflowResponse(value, "HOW_TO");

    expect(normalized.errorCode).toBe(null);
    expect(normalized.result.answer).toBe(answer);
    expect(normalized.result.citations[0].path[0]).toContain("<img");
    expect(globalThis.pwned).toBe(undefined);
});

test("explicit workflow routing uses one Odoo endpoint and preserves the selection", async () => {
    for (const workflow of ["EXPLAIN", "QUERY", "HOW_TO"]) {
        const panelState = state(workflow);
        let observedPath;
        let observedPayload;
        const executed = await submitAssistantRequest({
            state: panelState,
            screenContext: { capture: () => SCREEN },
            rpcCall: async (path, payload) => {
                observedPath = path;
                observedPayload = payload;
                return response(workflow);
            },
            message: "Pregunta",
        });

        expect(executed).toBe(true);
        expect(observedPath).toBe("/odoo_ai/v1/turn");
        expect(observedPayload.workflow).toBe(workflow);
        expect(panelState.result.workflow).toBe(workflow);
    }
});

test("workflow-confused response fails closed", async () => {
    const panelState = state("QUERY");

    await submitAssistantRequest({
        state: panelState,
        screenContext: { capture: () => SCREEN },
        rpcCall: async () => response("HOW_TO"),
        message: "Consulta",
    });

    expect(panelState.result).toBe(null);
    expect(panelState.errorCode).toBe("invalid_response");
});

test("unknown workflow is rejected before any RPC", async () => {
    const panelState = state("ACTION");
    let calls = 0;

    const executed = await submitAssistantRequest({
        state: panelState,
        screenContext: { capture: () => SCREEN },
        rpcCall: async () => {
            calls += 1;
            return {};
        },
        message: "Haz un write",
    });

    expect(executed).toBe(false);
    expect(calls).toBe(0);
    expect(panelState.errorCode).toBe("invalid_workflow");
});

test("loading guard prevents a second simultaneous turn", async () => {
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
        message: "¿Por qué?",
    };

    const first = submitExplainRequest(options);
    const second = await submitExplainRequest(options);

    expect(second).toBe(false);
    expect(calls).toBe(1);
    resolveRpc(response("EXPLAIN"));
    await first;
    expect(panelState.loading).toBe(false);
    expect(calls).toBe(1);
});
