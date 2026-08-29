import { expect, test } from "@odoo/hoot";
import {
    normalizeReferenceResponse,
    openPublicReference,
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
        navigation: { view_type: "form" },
        ...overrides,
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

test("revoked or unavailable reference never reaches action service", async () => {
    const actions = [];
    const opened = await openPublicReference(
        { kind: "odoo_record", model: "res.partner", record_id: 7, label: "Acme" },
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
