import { expect, test } from "@odoo/hoot";
import {
    formatScreenContext,
    shouldSubmitComposerKey,
    submitComposerMessage,
} from "@odoo_ai_assistant/components/assistant_panel/assistant_composer";

test("screen context keeps the technical model without the view type", () => {
    expect(
        formatScreenContext({
            model: "sale.order",
            res_id: 42,
            view_type: "form",
        })
    ).toBe("sale.order #42");

    expect(
        formatScreenContext({
            model: "res.partner",
            res_id: null,
            view_type: "kanban",
        })
    ).toBe("res.partner");
});

test("enter submits while shift-enter keeps a newline", () => {
    expect(shouldSubmitComposerKey({ key: "Enter", shiftKey: false, isComposing: false })).toBe(true);
    expect(shouldSubmitComposerKey({ key: "Enter", shiftKey: true, isComposing: false })).toBe(false);
    expect(shouldSubmitComposerKey({ key: "Enter", shiftKey: false, isComposing: true })).toBe(false);
    expect(shouldSubmitComposerKey({ key: "a", shiftKey: false, isComposing: false })).toBe(false);
});

test("composer shows the user message immediately and keeps it on success", async () => {
    const state = {
        draft: "  Revisa este pedido  ",
        loading: false,
        decisionLoading: false,
        errorCode: null,
        messages: [],
    };
    const component = {
        state,
        recoveryPending: false,
        panel: {
            setDraft(value) {
                state.draft = value;
            },
            async submit(message) {
                expect(message).toBe("Revisa este pedido");
                expect(state.draft).toBe("");
                expect(state.messages).toHaveLength(1);
                expect(state.messages[0].role).toBe("user");
                expect(state.messages[0].content).toBe("Revisa este pedido");
                state.messages = [
                    ...state.messages,
                    {
                        message_id: "local-user-turn-1",
                        role: "user",
                        content: message,
                        created_at: "2026-08-25T12:00:00Z",
                    },
                    {
                        message_id: "local-assistant-turn-1",
                        role: "assistant",
                        content: "Hecho",
                        created_at: "2026-08-25T12:00:01Z",
                    },
                ];
                return true;
            },
        },
    };

    expect(await submitComposerMessage(component)).toBe(true);
    expect(state.draft).toBe("");
    expect(state.messages).toHaveLength(2);
    expect(state.messages[0].message_id).toBe("local-user-turn-1");
    expect(state.messages[1].role).toBe("assistant");
});

test("composer rolls back the optimistic message and restores the draft on failure", async () => {
    const state = {
        draft: "  mensaje pendiente  ",
        loading: false,
        decisionLoading: false,
        errorCode: null,
        messages: [],
    };
    const draftChanges = [];
    const component = {
        state,
        recoveryPending: false,
        panel: {
            setDraft(value) {
                state.draft = value;
                draftChanges.push(value);
            },
            async submit() {
                expect(state.messages).toHaveLength(1);
                return false;
            },
        },
    };

    expect(await submitComposerMessage(component)).toBe(false);
    expect(state.messages).toEqual([]);
    expect(state.draft).toBe("  mensaje pendiente  ");
    expect(draftChanges).toEqual(["", "  mensaje pendiente  "]);
});
