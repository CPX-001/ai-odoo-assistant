import { expect, test } from "@odoo/hoot";
import {
    finalAnswerReferences,
    finalReferenceActionLabel,
    referenceKey,
} from "@odoo_ai_assistant/components/assistant_panel/assistant_navigation_references";

function references() {
    return [
        {
            kind: "odoo_action",
            action_id: 41,
            model: "res.partner",
            label: "Contactos",
            description: "Abrir Contactos",
        },
        {
            kind: "odoo_view",
            view_id: 51,
            model: "res.partner",
            label: "Contactos lista",
            description: "Abrir vista Contactos",
        },
        {
            kind: "odoo_menu",
            action_id: 41,
            menu_id: 61,
            model: "res.partner",
            label: "Contactos",
            description: "Menú Contactos",
        },
        {
            kind: "odoo_setting",
            action_id: 71,
            setting_field: "group_use_lead",
            model: "res.config.settings",
            label: "Leads",
            description: "Configurar leads",
        },
        {
            kind: "odoo_setting",
            action_id: 71,
            setting_field: "group_use_recurring_revenues",
            model: "res.config.settings",
            label: "Ingresos recurrentes",
            description: "Configurar ingresos recurrentes",
        },
    ];
}

test("final answer exposes only structured host navigation references", () => {
    const result = { answer: "Puedes encontrarlo aquí", references: references() };
    const parsed = finalAnswerReferences(result);
    expect(parsed).toHaveLength(5);
    expect(parsed.map((item) => item.kind)).toEqual([
        "odoo_action",
        "odoo_view",
        "odoo_menu",
        "odoo_setting",
        "odoo_setting",
    ]);
    expect(finalAnswerReferences({ references: [{ kind: "url", url: "/web#unsafe" }] })).toEqual([]);
});

test("reference keys distinguish settings sharing one action and remain type scoped", () => {
    const parsed = references();
    const keys = parsed.map(referenceKey);
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys[3]).toBe("odoo_setting:71:group_use_lead");
    expect(keys[4]).toBe("odoo_setting:71:group_use_recurring_revenues");
    expect(referenceKey(parsed[2])).toBe("odoo_menu:61");
    expect(referenceKey(parsed[1])).toBe("odoo_view:res.partner:51");
});

test("final navigation labels use understandable action wording", () => {
    const parsed = references();
    expect(finalReferenceActionLabel(parsed[0])).toBe("Abrir Contactos");
    expect(finalReferenceActionLabel(parsed[2])).toBe("Ir a Contactos");
    expect(finalReferenceActionLabel(parsed[3])).toBe("Abrir Leads");
});
