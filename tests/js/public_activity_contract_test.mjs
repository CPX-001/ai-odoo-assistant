import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const source = await fs.readFile(
    path.join(root, "addons/odoo_ai_assistant/static/src/services/assistant_public_activity_contract.js"),
    "utf8"
);
const contract = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const activityId = "activity:v1:0123456789abcdef0123456789abcdef";
const event = (sequence, overrides = {}) => ({
    sequence,
    turn_id: "turn-public-0001",
    kind: "capability.started",
    phase: "capability",
    status: "running",
    label: "Consultando sale.order",
    resource: { model: "sale.order", record_ids: [7], display_names: ["S0007"] },
    references: [],
    capability: "odoo.query_records",
    progress: null,
    diagnostic_code: null,
    occurred_at: "2026-08-28T10:00:00.000000Z",
    activity_id: activityId,
    ...overrides,
});
assert.equal(contract.normalizePublicTurnEvent(event(1)).activity_id, activityId);
assert.equal(contract.normalizePublicTurnEvent(event(1, { kind: "agent.thinking" })), null);
assert.equal(contract.normalizePublicTurnEvent(event(1, { activity_id: "operation-42" })), null);
assert.equal(contract.normalizePublicTurnEvent({ ...event(1), payload: { prompt: "private" } }), null);
const fiftyIds = Array.from({ length: 50 }, (_value, index) => index + 1);
assert.equal(
    contract.normalizePublicTurnEvent(
        event(1, {
            resource: {
                model: "sale.order",
                record_ids: fiftyIds,
                display_names: fiftyIds.map((recordId) => `S${String(recordId).padStart(4, "0")}`),
            },
        })
    ).resource.record_ids.length,
    50
);
assert.equal(
    contract.normalizePublicTurnEvent(
        event(1, {
            resource: {
                model: "sale.order",
                record_ids: [...fiftyIds, 51],
                display_names: [],
            },
        })
    ),
    null
);
const navigation = {
    kind: "odoo_setting",
    label: "Impuestos",
    description: "Abrir configuración de impuestos",
    model: "res.config.settings",
    action_id: 71,
    setting_field: "tax_calculation_rounding_method",
};
assert.equal(
    contract.normalizePublicTurnEvent(event(1, { references: [navigation] })).references[0].kind,
    "odoo_setting"
);
assert.equal(
    contract.normalizePublicTurnEvent(
        event(1, { references: [{ ...navigation, route: "/web#unsafe" }] })
    ),
    null
);
assert.deepEqual(
    contract.normalizePublicTurnEventBatch([event(4), event(5)], { afterSequence: 3 }).map((x) => x.sequence),
    [4, 5]
);
assert.equal(contract.normalizePublicTurnEventBatch([event(5), event(4)], { afterSequence: 3 }), null);
console.log("public activity contract: 10 assertions passed");
