/** Real Chromium P5.3 stable-settings validation through the Odoo product path. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const GATE = "P5-REAL-SETTINGS-SNAPSHOT";
const TERMINAL_STATES = new Set([
    "completed",
    "failed",
    "cancelled",
    "recovery_required",
]);
const PROFILE_POLICY = Object.freeze({
    strict: { confirmation_mode: "always_confirm", max_auto_risk: "low" },
    balanced: { confirmation_mode: "risk_based", max_auto_risk: "moderate" },
    autonomous: { confirmation_mode: "protected_only", max_auto_risk: "high" },
    full_access: { confirmation_mode: "protected_only", max_auto_risk: "protected" },
});
const PROFILE_LABEL = Object.freeze({
    strict: "Estricto",
    balanced: "Equilibrado",
    autonomous: "Autónomo",
    full_access: "Acceso completo",
});

function required(name) {
    const value = process.env[name]?.trim();
    assert.ok(value, `${name} is required`);
    return value;
}

function option(name) {
    const index = process.argv.indexOf(name);
    return index >= 0 ? process.argv[index + 1] : undefined;
}

async function jsonRpc(page, path, params) {
    const envelope = await page.evaluate(
        async ({ rpcPath, rpcParams }) => {
            const response = await fetch(rpcPath, {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: rpcParams,
                    id: Date.now(),
                }),
            });
            return response.json();
        },
        { rpcPath: path, rpcParams: params }
    );
    assert.ok(!envelope.error, JSON.stringify(envelope.error));
    return envelope.result;
}

async function datasetCall(page, model, method, args = [], kwargs = {}) {
    return jsonRpc(page, `/web/dataset/call_kw/${model}/${method}`, {
        model,
        method,
        args,
        kwargs,
    });
}

async function login(page, { baseUrl, database, loginName, password }) {
    await page.goto(`${baseUrl}/web/login?db=${encodeURIComponent(database)}`);
    await page.locator('input[name="login"]').fill(loginName);
    await page.locator('input[name="password"]').fill(password);
    await Promise.all([
        page.waitForURL((url) => !url.pathname.endsWith("/web/login"), { timeout: 60_000 }),
        page.locator('button[type="submit"]').click(),
    ]);
    await page.goto(`${baseUrl}/web?db=${encodeURIComponent(database)}`);
    await page.getByRole("button", { name: "Abrir AI Assistant" }).click();
    await page.locator("#o_ai_assistant_question").waitFor({ state: "visible", timeout: 60_000 });
}

function longPrompt(token) {
    return `${token} Responde en español con exactamente dieciocho frases numeradas sobre métodos generales de organización del trabajo. Cada frase debe tener al menos dieciocho palabras. No uses herramientas de Odoo ni realices cambios.`;
}

async function startTurn(page, prompt) {
    const composer = page.locator("#o_ai_assistant_question");
    await composer.waitFor({ state: "visible", timeout: 30_000 });
    assert.equal(await composer.isEnabled(), true, "active conversation composer is unexpectedly disabled");
    await composer.fill(prompt);
    const responsePromise = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/turn" &&
            response.request().method() === "POST",
        { timeout: 60_000 }
    );
    await page.getByRole("button", { name: "Enviar mensaje" }).click();
    const envelope = await (await responsePromise).json();
    assert.ok(!envelope.error, JSON.stringify(envelope.error));
    const queued = envelope.result;
    assert.equal(queued?.ok, true);
    assert.equal(typeof queued.turn_id, "string");
    assert.equal(typeof queued.conversation_id, "string");
    return queued;
}

async function turnStatus(page, turnId) {
    const status = await jsonRpc(page, "/odoo_ai/v1/turn/status", {
        turn_id: turnId,
        after_sequence: 0,
    });
    assert.equal(status?.ok, true);
    assert.equal(status.turn_id, turnId);
    return status;
}

async function requireUnresolved(page, turnId) {
    const status = await turnStatus(page, turnId);
    assert.ok(
        !TERMINAL_STATES.has(status.state),
        "Turn A became terminal before selectors could be changed; use a longer safe prompt"
    );
}

async function cancelIfUnresolved(page, turnId) {
    if (!turnId) return;
    try {
        const status = await turnStatus(page, turnId);
        if (!TERMINAL_STATES.has(status.state)) {
            await jsonRpc(page, "/odoo_ai/v1/turn/cancel", { turn_id: turnId });
        }
    } catch {
        // Best-effort cleanup; the disposable database remains the safety boundary.
    }
}

async function turnSnapshot(page, turnId) {
    for (let attempt = 0; attempt < 50; attempt += 1) {
        const rows = await datasetCall(
            page,
            "odoo.ai.turn",
            "search_read",
            [[["turn_uuid", "=", turnId]]],
            {
                fields: [
                    "turn_uuid",
                    "reasoning_model",
                    "policy_payload",
                    "execution_settings_payload",
                    "state",
                    "attempt_count",
                ],
                limit: 1,
            }
        );
        if (Array.isArray(rows) && rows.length === 1) return rows[0];
        await page.waitForTimeout(100);
    }
    assert.fail(`persisted turn ${turnId} was not readable by its owning user`);
}

function normalizedModel(value) {
    return typeof value === "string" && value ? value : null;
}

function userPolicy(row) {
    const value = row?.policy_payload?.layers?.user;
    assert.ok(value && typeof value === "object", "turn policy snapshot has no user layer");
    return value;
}

function assertProfilePolicy(row, profile) {
    const expected = PROFILE_POLICY[profile];
    assert.ok(expected, `unsupported profile ${profile}`);
    const actual = userPolicy(row);
    assert.equal(actual.confirmation_mode, expected.confirmation_mode);
    assert.equal(actual.max_auto_risk, expected.max_auto_risk);
}

function assertExecutionSnapshot(row, expectedModel, expectedProfile) {
    const snapshot = row.execution_settings_payload;
    assert.ok(snapshot && typeof snapshot === "object", "turn has no execution_settings_payload");
    assert.deepEqual(
        Object.keys(snapshot).sort(),
        ["autonomy_profile", "format_version", "policy", "reasoning_model"],
        "unexpected execution settings snapshot shape"
    );
    assert.equal(snapshot.format_version, 1);
    assert.equal(normalizedModel(snapshot.reasoning_model), expectedModel);
    assert.equal(snapshot.autonomy_profile, expectedProfile);
    assert.deepEqual(snapshot.policy, row.policy_payload);
    assert.equal(normalizedModel(row.reasoning_model), expectedModel);
    assertProfilePolicy(row, expectedProfile);
    return structuredClone(snapshot);
}

async function readPreferences(page) {
    const models = await jsonRpc(page, "/odoo_ai/v1/chat-models", {});
    const autonomy = await jsonRpc(page, "/odoo_ai/v1/agent-autonomy", {});
    assert.equal(models?.ok, true);
    assert.ok(Array.isArray(models.models));
    assert.equal(autonomy?.ok, true);
    assert.ok(PROFILE_POLICY[autonomy.profile]);
    return { models, autonomyProfile: autonomy.profile };
}

async function changeModelThroughUi(page, modelPreferences) {
    const button = page.getByRole("button", { name: "Modelo de Codex" });
    await button.waitFor({ state: "visible", timeout: 30_000 });
    assert.equal(await button.isEnabled(), true, "model selector is blocked by Turn A");

    let targetModel;
    if (modelPreferences.selected_model) {
        targetModel = null;
    } else {
        assert.ok(
            modelPreferences.models.length > 0,
            "P5.3 real settings gate needs at least one selectable Codex model"
        );
        targetModel = modelPreferences.models[0].model;
    }

    await button.click();
    const responsePromise = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/chat-model" &&
            response.request().method() === "POST",
        { timeout: 30_000 }
    );
    const optionText = targetModel === null ? "Predeterminado" : targetModel;
    const pickerOptions = page.locator(".o_ai_assistant_picker_option").filter({ hasText: optionText });
    assert.ok(await pickerOptions.count(), `expected a model option for ${optionText}`);
    await pickerOptions.last().click();
    const envelope = await (await responsePromise).json();
    assert.ok(!envelope.error, JSON.stringify(envelope.error));
    assert.equal(envelope.result?.ok, true);
    assert.equal(envelope.result.selected_model ?? null, targetModel);
    return targetModel;
}

async function changeAutonomyThroughUi(page, currentProfile) {
    const targetProfile = currentProfile === "strict" ? "balanced" : "strict";
    const button = page.getByRole("button", { name: "Nivel de autonomía del Assistant" });
    await button.waitFor({ state: "visible", timeout: 30_000 });
    assert.equal(await button.isEnabled(), true, "autonomy selector is blocked by Turn A");
    await button.click();
    const responsePromise = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/agent-autonomy-set" &&
            response.request().method() === "POST",
        { timeout: 30_000 }
    );
    const pickerOptions = page.locator(".o_ai_assistant_picker_option").filter({
        hasText: PROFILE_LABEL[targetProfile],
    });
    assert.ok(await pickerOptions.count(), `expected an autonomy option for ${targetProfile}`);
    await pickerOptions.last().click();
    const envelope = await (await responsePromise).json();
    assert.ok(!envelope.error, JSON.stringify(envelope.error));
    assert.equal(envelope.result?.ok, true);
    assert.equal(envelope.result.profile, targetProfile);
    return targetProfile;
}

async function restorePreferences(page, originalModel, originalProfile) {
    try {
        await jsonRpc(page, "/odoo_ai/v1/chat-model", { model: originalModel });
    } catch {
        // Best-effort cleanup.
    }
    try {
        await jsonRpc(page, "/odoo_ai/v1/agent-autonomy-set", { profile: originalProfile });
    } catch {
        // Best-effort cleanup.
    }
}

async function runGate(page, stamp) {
    const original = await readPreferences(page);
    const originalModel = original.models.selected_model ?? null;
    const originalProfile = original.autonomyProfile;
    const tokenA = `P53-SNAP-A-${stamp}`;
    const tokenB = `P53-SNAP-B-${stamp}`;
    let turnA = null;
    let turnB = null;
    try {
        turnA = await startTurn(page, longPrompt(tokenA));
        await requireUnresolved(page, turnA.turn_id);
        const before = await turnSnapshot(page, turnA.turn_id);
        const capturedA = assertExecutionSnapshot(before, originalModel, originalProfile);

        const selectedModel = await changeModelThroughUi(page, original.models);
        const selectedProfile = await changeAutonomyThroughUi(page, originalProfile);

        const after = await turnSnapshot(page, turnA.turn_id);
        assert.equal(normalizedModel(after.reasoning_model), originalModel);
        assert.deepEqual(userPolicy(after), userPolicy(before));
        assert.deepEqual(after.execution_settings_payload, capturedA);
        assertExecutionSnapshot(after, originalModel, originalProfile);

        const newChat = page.getByRole("button", { name: "Nuevo chat" });
        await newChat.waitFor({ state: "visible", timeout: 30_000 });
        assert.equal(await newChat.isEnabled(), true, "new chat is blocked while Turn A is unresolved");
        await newChat.click();
        await page.locator("#o_ai_assistant_question").waitFor({ state: "visible", timeout: 30_000 });

        turnB = await startTurn(page, longPrompt(tokenB));
        const snapshotB = await turnSnapshot(page, turnB.turn_id);
        assertExecutionSnapshot(snapshotB, selectedModel, selectedProfile);
        assert.notDeepEqual(snapshotB.execution_settings_payload, capturedA);

        console.log(
            JSON.stringify({
                gate: GATE,
                turn_a: turnA.turn_id,
                turn_b: turnB.turn_id,
                snapshot_format: 1,
                original_model: originalModel,
                next_model: selectedModel,
                original_profile: originalProfile,
                next_profile: selectedProfile,
                approval_resume: "covered_by_deterministic_gate_not_applicable_to_read_only_browser_fixture",
                result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
            })
        );
    } finally {
        await restorePreferences(page, originalModel, originalProfile);
        await cancelIfUnresolved(page, turnA?.turn_id);
        await cancelIfUnresolved(page, turnB?.turn_id);
    }
}

const gateId = option("--gate");
assert.equal(gateId, GATE, `--gate must be ${GATE}`);
const baseUrl = required("ODOO_AI_P5_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P5_DB");
const loginName = required("ODOO_AI_P5_LOGIN");
const password = required("ODOO_AI_P5_PASSWORD");
assert.ok(database.startsWith("odoo_ai_"), "P5.3 gate requires a disposable odoo_ai_* database");
const stamp = Date.now().toString(36);

const browser = await chromium.launch({ headless: true });
try {
    const context = await browser.newContext();
    const page = await context.newPage();
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
    await login(page, { baseUrl, database, loginName, password });
    await runGate(page, stamp);
    assert.deepEqual(browserErrors, []);
    await context.close();
} finally {
    await browser.close();
}
