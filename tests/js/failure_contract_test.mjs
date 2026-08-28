import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const source = await fs.readFile(
    path.join(root, "addons/odoo_ai_assistant/static/src/services/assistant_failure_contract.js"),
    "utf8"
);
const contract = await import(
    `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

const base = {
    code: "codex_turn_failed",
    category: "provider_capacity",
    stage: "provider",
    component: "codex",
    retryability: "safe",
    effect_state: "none",
    user_action: "retry",
    safe_summary: "Provider capacity unavailable",
    safe_details: { http_status: 503 },
    diagnostic_id: "diag-p24-node-01",
    provider_code: "serverOverloaded",
};

const parsed = contract.normalizeFailureEnvelope(base, base.code);
assert.equal(parsed.category, "provider_capacity");
assert.equal(contract.failureCanRetry(parsed), true);
assert.equal(
    contract.failureCanRetry(contract.normalizeFailureEnvelope({ ...base, effect_state: "unknown" })),
    false
);
assert.equal(contract.normalizeFailureEnvelope({ ...base, unexpected: true }), null);
assert.equal(contract.normalizeFailureEnvelope({ ...base, safe_details: { stderr: "secret" } }), null);

const error = contract.failureErrorFromStatus({
    state: "failed",
    error_code: base.code,
    failure: base,
});
assert.equal(error.failure.diagnostic_id, base.diagnostic_id);
assert.equal(contract.failureFromError(new Error("connection_lost")).code, "connection_lost");

const recovery = contract.failureErrorFromStatus({
    state: "recovery_required",
    error_code: base.code,
    failure: base,
});
assert.equal(recovery.failure.effect_state, "unknown");
assert.equal(recovery.failure.retryability, "never");
assert.equal(recovery.failure.user_action, "review");
assert.equal(contract.failureCanRetry(recovery.failure), false);

const partial = contract.failureErrorFromStatus({
    state: "recovery_required",
    error_code: base.code,
    failure: {
        ...base,
        effect_state: "partial",
        retryability: "safe",
        user_action: "retry",
    },
});
assert.equal(partial.failure.effect_state, "partial");
assert.equal(partial.failure.retryability, "never");
assert.equal(partial.failure.user_action, "review");

console.log("failure contract: 14 assertions passed");
