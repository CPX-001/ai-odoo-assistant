import { expect, test } from "@odoo/hoot";
import { withoutChatErrorSideEffect } from "@odoo_ai_assistant/services/assistant_history_error_isolation";

test("auxiliary history failure does not create a chat-turn error", async () => {
    const state = { errorCode: null };

    const result = await withoutChatErrorSideEffect(state, async () => {
        state.errorCode = "service_unavailable";
        return false;
    });

    expect(result).toBe(false);
    expect(state.errorCode).toBe(null);
});

test("auxiliary history success does not clear an existing chat-turn error", async () => {
    const state = { errorCode: "engine_timeout" };

    const result = await withoutChatErrorSideEffect(state, async () => {
        state.errorCode = null;
        return true;
    });

    expect(result).toBe(true);
    expect(state.errorCode).toBe("engine_timeout");
});
