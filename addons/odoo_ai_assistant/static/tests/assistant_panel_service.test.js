import { expect, test } from "@odoo/hoot";
import {
    normalizeExplainResponse,
    submitExplainRequest,
} from "@odoo_ai_assistant/services/assistant_panel_service";

const SCREEN = {
    model: "sale.order",
    res_id: 42,
    captured_at: "2026-08-22T10:30:00.000Z",
};

function state() {
    return {
        context: null,
        errorCode: null,
        loading: false,
        result: null,
    };
}

test("adversarial answer remains plain response data", () => {
    const answer = '<script>globalThis.pwned = true</script><a href="javascript:alert(1)">x</a>';
    const response = {
        ok: true,
        turn_id: "12345678-1234-5678-1234-567812345678",
        answer,
        confidence: "low",
        limitations: ["HTML is untrusted"],
        citations: [],
    };

    const normalized = normalizeExplainResponse(response);

    expect(normalized.errorCode).toBe(null);
    expect(normalized.result.answer).toBe(answer);
    expect(globalThis.pwned).toBe(undefined);
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
    resolveRpc({
        ok: true,
        turn_id: "12345678-1234-5678-1234-567812345678",
        answer: "Checked answer",
        confidence: "high",
        limitations: [],
        citations: [],
    });
    await first;
    expect(panelState.loading).toBe(false);
    expect(calls).toBe(1);
});
