/** @odoo-module **/

import { expect, test } from "@odoo/hoot";
import { normalizeResponseDetailPreferences } from "@odoo_ai_assistant/services/assistant_response_detail_service";

test("response detail accepts an inherited normal default", () => {
    expect(
        normalizeResponseDetailPreferences({
            ok: true,
            selected_response_detail: null,
            default_response_detail: "normal",
            effective_response_detail: "normal",
        })
    ).toEqual({ selected: null, defaultDetail: "normal", effective: "normal" });
});

test("response detail rejects unknown or inconsistent values", () => {
    expect(
        normalizeResponseDetailPreferences({
            ok: true,
            selected_response_detail: "concise",
            default_response_detail: "normal",
            effective_response_detail: "extensive",
        })
    ).toBe(null);
    expect(
        normalizeResponseDetailPreferences({
            ok: true,
            selected_response_detail: "tiny",
            default_response_detail: "normal",
            effective_response_detail: "tiny",
        })
    ).toBe(null);
});
