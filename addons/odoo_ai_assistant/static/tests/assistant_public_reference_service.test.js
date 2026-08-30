import { expect, test } from "@odoo/hoot";
import {
    normalizeHostNavigationReference,
    normalizeReferenceResponse,
    openPublicReference,
    publicReferenceRequest,
    referenceDisclosure,
    resourceModelReference,
    resourceReferences,
} from "@odoo_ai_assistant/services/assistant_public_reference_service";

function resolvedRecord(overrides = {}) {
    return {
        kind: "odoo_record",
        model: "res.partner",
        record_id: 7,
        label: "Acme",
        model_label: "Contacto",
        fields: [{ name: "name", label: "Nombre", value: "Acme" }],
        description: "Abrir Acme",
        navigation: { mode: "record", model: "res.partner", record_id: 7 },
        ...overrides,
    };
}

function resolvedNavigation(kind) {
    if (kind === "odoo_action") {
        return {
            kind,
            action_id: 41,
            model: "res.partner",
            label: "Contactos",
            description: "Abrir Contactos",
            navigation: { mode: "action", action_id: 41 },
        };
    }
    if (kind === "odoo_view") {
        return {
            kind,
            view_id: 51,
            model: "res.partner",
            label: "Contactos lista",
            description: "Abrir vista de contactos",
            navigation: {
                mode: "view",
                model: "res.partner",
                view_id: 51,
                view_type: "list",
            },
        };
    }
    if (kind === "odoo_menu") {
        return {
            kind,
            action_id: 41,
            menu_id: 61,
            model: "res.partner",
            label: "Contactos",
            description: "Menú visible de Contactos",
            navigation: { mode: "action", action_id: 41 },
        };
    }
    return {
        kind: "odoo_setting",
        action_id: 71,
        setting_field: "group_use_lead",
        model: "res.config.settings",
        label: "Leads",
        description: "Opción instalada de configuración",
        navigation: { mode: "action", action_id: 71 },
    };
}

test("resource record identities become typed references and disclose five by default", () => {
    const references = resourceReferences({
        model: "res.partner",
        record_ids: [1, 2, 3, 4, 5, 6, 7],
        display_names: ["A", "B", "C", "D", "E", "F", "G"],
    });
    const page = referenceDisclosure(references);

    expect(references).toHaveLength(7);
    expect(page.visible).toHaveLength(5);
    expect(page.remaining_count).toBe(2);
    expect(page.next_count).toBe(2);
    expect(page.can_show_more).toBe(true);
    expect(page.can_show_remaining).toBe(true);
    expect(resourceModelReference({ model: "res.partner" })).toEqual({
        kind: "odoo_model",
        model: "res.partner",
    });
});

test("show remaining is bounded and leaves list navigation as the overload fallback", () => {
    const references = Array.from({ length: 30 }, (_value, index) => ({
        kind: "odoo_record",
        model: "res.partner",
        record_id: index + 1,
        label: `Partner ${index + 1}`,
    }));
    const page = referenceDisclosure(references, {
        pageSize: 5,
        visibleCount: 10,
        maximumRows: 20,
    });

    expect(page.visible).toHaveLength(10);
    expect(page.total_count).toBe(30);
    expect(page.remaining_count).toBe(20);
    expect(page.can_show_more).toBe(true);
    expect(page.can_show_remaining).toBe(false);
    expect(page.remaining_blocked).toBe(true);
    expect(page.maximum_rows).toBe(20);
});

test("resolved reference response is a closed host contract", () => {
    const parsed = normalizeReferenceResponse({
        ok: true,
        references: [{ ok: true, reference: resolvedRecord() }],
    });
    expect(parsed[0].label).toBe("Acme");

    expect(
        normalizeReferenceResponse({
            ok: true,
            references: [
                {
                    ok: true,
                    reference: resolvedRecord({ route: "/web#unsafe" }),
                },
            ],
        })
    ).toBe(null);
    expect(
        normalizeReferenceResponse({
            ok: true,
            references: [{ ok: true, reference: resolvedRecord({ navigation: { route: "/unsafe" } }) }],
        })
    ).toBe(null);
});

test("host navigation references accept only model action view menu and setting shapes", () => {
    const hostReferences = [
        {
            kind: "odoo_model",
            model: "res.partner",
            label: "Contactos",
            description: "Abrir contactos",
        },
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
            setting_field: "group_use_lead",
            model: "res.config.settings",
            label: "Leads",
            description: "Configurar leads",
        },
    ];
    for (const reference of hostReferences) {
        expect(normalizeHostNavigationReference(reference)?.kind).toBe(reference.kind);
    }
    expect(normalizeHostNavigationReference({ ...hostReferences[1], route: "/unsafe" })).toBe(null);
    expect(
        normalizeHostNavigationReference({
            ...hostReferences[4],
            model: "ir.config_parameter",
        })
    ).toBe(null);
});

test("browser sends only closed identifiers back to Odoo before navigation", () => {
    expect(publicReferenceRequest(resolvedNavigation("odoo_action"))).toEqual({
        kind: "odoo_action",
        action_id: 41,
    });
    expect(publicReferenceRequest(resolvedNavigation("odoo_view"))).toEqual({
        kind: "odoo_view",
        view_id: 51,
    });
    expect(publicReferenceRequest(resolvedNavigation("odoo_menu"))).toEqual({
        kind: "odoo_menu",
        menu_id: 61,
    });
    expect(publicReferenceRequest(resolvedNavigation("odoo_setting"))).toEqual({
        kind: "odoo_setting",
        action_id: 71,
        setting_field: "group_use_lead",
    });
    expect(publicReferenceRequest({ kind: "raw_url", url: "/web#id=7" })).toBe(null);
});

test("opening a record revalidates it before constructing an Odoo action", async () => {
    const actions = [];
    const opened = await openPublicReference(
        { kind: "odoo_record", model: "res.partner", record_id: 7, label: "Acme" },
        {
            rpcCall: async (route, payload) => {
                expect(route).toBe("/odoo_ai/v1/public-references");
                expect(payload.references).toEqual([
                    { kind: "odoo_record", model: "res.partner", record_id: 7 },
                ]);
                return {
                    ok: true,
                    references: [{ ok: true, reference: resolvedRecord() }],
                };
            },
            actionService: {
                async doAction(action) {
                    actions.push(action);
                },
            },
        }
    );

    expect(opened).toBe(true);
    expect(actions).toEqual([
        {
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: 7,
            target: "current",
            views: [[false, "form"]],
        },
    ]);
});

test("action view menu and setting navigation use only revalidated server descriptors", async () => {
    const actions = [];
    for (const kind of ["odoo_action", "odoo_view", "odoo_menu", "odoo_setting"]) {
        const raw = resolvedNavigation(kind);
        const opened = await openPublicReference(raw, {
            rpcCall: async (_route, payload) => ({
                ok: true,
                references: [{ ok: true, reference: resolvedNavigation(kind) }],
                request: payload,
            }),
            actionService: {
                async doAction(action) {
                    actions.push(action);
                },
            },
        });
        expect(opened).toBe(true);
    }
    expect(actions).toEqual([
        41,
        {
            type: "ir.actions.act_window",
            res_model: "res.partner",
            target: "current",
            views: [[51, "list"]],
        },
        41,
        71,
    ]);
});

test("revoked or unavailable reference never reaches action service", async () => {
    const actions = [];
    const opened = await openPublicReference(
        { kind: "odoo_action", action_id: 41, model: "res.partner", label: "Contactos" },
        {
            rpcCall: async () => ({
                ok: true,
                references: [{ ok: false, error: { code: "reference_unavailable" } }],
            }),
            actionService: {
                async doAction(action) {
                    actions.push(action);
                },
            },
        }
    );

    expect(opened).toBe(false);
    expect(actions).toEqual([]);
});
