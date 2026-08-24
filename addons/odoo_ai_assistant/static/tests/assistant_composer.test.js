import { expect, test } from "@odoo/hoot";
import {
    formatScreenContext,
    shouldSubmitComposerKey,
} from "@odoo_ai_assistant/components/assistant_panel/assistant_composer";

test("screen context shows Odoo model record and current view", () => {
    expect(
        formatScreenContext({
            model: "sale.order",
            res_id: 42,
            view_type: "form",
        })
    ).toBe("sale.order #42 · Formulario");

    expect(
        formatScreenContext({
            model: "res.partner",
            res_id: null,
            view_type: "kanban",
        })
    ).toBe("res.partner · Kanban");
});

test("enter submits while shift-enter keeps a newline", () => {
    expect(shouldSubmitComposerKey({ key: "Enter", shiftKey: false, isComposing: false })).toBe(true);
    expect(shouldSubmitComposerKey({ key: "Enter", shiftKey: true, isComposing: false })).toBe(false);
    expect(shouldSubmitComposerKey({ key: "Enter", shiftKey: false, isComposing: true })).toBe(false);
    expect(shouldSubmitComposerKey({ key: "a", shiftKey: false, isComposing: false })).toBe(false);
});
