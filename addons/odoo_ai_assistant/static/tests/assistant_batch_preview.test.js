/** @odoo-module **/

import { expect, test } from "@odoo/hoot";

import {
    batchPreviewOmitted,
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

test("bulk delete preview shows records, protected exclusions, and omitted count", () => {
    const step = {
        step_id: "bulk-delete",
        preview: {
            records: [
                { record_id: 10, display_name: "Contacto de prueba" },
                { record_id: 11, display_name: "Otro contacto" },
            ],
            protected_records: [
                {
                    record_id: 1,
                    display_name: "Administrador",
                    reason: "linked_active_user",
                },
            ],
            count: 27,
            requested_count: 28,
            excluded_count: 1,
            omitted_count: 25,
        },
    };

    expect(batchPreviewRows(step, true).map((row) => row.label)).toEqual([
        "Contacto de prueba",
        "Otro contacto",
        "Administrador",
    ]);
    expect(batchPreviewRows(step, true).at(-1).excluded).toBe(true);
    expect(batchPreviewOmitted(step)).toBe(25);
});
