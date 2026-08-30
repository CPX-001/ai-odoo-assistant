import { expect, test } from "@odoo/hoot";
import { reduceSemanticActivity } from "@odoo_ai_assistant/services/assistant_semantic_activity";

const ACTIVITY = "activity:v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

function event(sequence, status, references = []) {
    return {
        sequence,
        turn_id: "turn-public-navigation-0001",
        kind: status === "running" ? "capability.started" : "capability.completed",
        phase: "capability",
        status,
        label: "Buscando dónde abrirlo en Odoo",
        resource: null,
        references,
        capability: "odoo.resolve_navigation",
        progress: null,
        diagnostic_code: null,
        occurred_at: `2026-08-30T00:00:0${sequence}.000000Z`,
        activity_id: ACTIVITY,
        semantic: null,
    };
}

test("semantic activity keeps host-resolved action view menu and setting chips on completion", () => {
    const references = [
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
            description: "Abrir vista",
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
            setting_field: "company_id",
            model: "res.config.settings",
            label: "Compañía",
            description: "Abrir configuración",
        },
    ];
    const items = reduceSemanticActivity([event(1, "running"), event(2, "completed", references)]);

    expect(items).toHaveLength(1);
    expect(items[0].status).toBe("completed");
    expect(items[0].references).toEqual(references);
    expect(items[0].references.map((item) => item.kind)).toEqual([
        "odoo_action",
        "odoo_view",
        "odoo_menu",
        "odoo_setting",
    ]);
});
