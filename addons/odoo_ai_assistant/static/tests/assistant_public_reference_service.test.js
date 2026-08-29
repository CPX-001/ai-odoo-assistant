import { expect, test } from "@odoo/hoot";
import {
    normalizeReferenceResponse,
    openPublicReference,
    referenceDisclosure,
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
            actionService: { async doAction(action) { actions.push(action); } },
        }
    );

    expect(opened).toBe(false);
    expect(actions).toEqual([]);
});
