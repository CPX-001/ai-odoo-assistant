/** @odoo-module **/

import { expect, test } from "@odoo/hoot";

import {
    batchPreviewRemaining,
    batchPreviewRows,
} from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

test("batch approval preview shows five rows before progressive disclosure", () => {
    const step = {
        step_id: "batch-create",
        preview: {
            rows: Array.from({ length: 30 }, (_value, index) => ({
                name: `Contacto ${String(index + 1).padStart(2, "0")}`,
            })),
        },
    };

    expect(batchPreviewRows(step).map((row) => row.label)).toEqual([
        "Contacto 01",
        "Contacto 02",
        "Contacto 03",
        "Contacto 04",
        "Contacto 05",
    ]);
    expect(batchPreviewRemaining(step)).toBe(25);
    expect(batchPreviewRows(step, true)).toHaveLength(30);
    expect(batchPreviewRemaining(step, true)).toBe(0);
});
