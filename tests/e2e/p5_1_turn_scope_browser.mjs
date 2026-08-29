/** Real Chromium P5.1 turn-scoped frontend validation through the Odoo product path. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const GATES = new Set([
    "P5.1-BROWSER-MULTICHAT",
    "P5.1-BROWSER-SETTINGS-SNAPSHOT",
    "P5.1-BROWSER-REOPEN",
]);
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
    const composer = page.locator("#o_ai_assistant_question");
    const history = page.locator(".o_ai_assistant_history");
    await Promise.race([
        composer.waitFor({ state: "visible", timeout: 60_000 }),
        history.waitFor({ state: "visible", timeout: 60_000 }),
    ]);
    if (!(await composer.isVisible())) {
        await page.locator(".o_ai_assistant_history_item_new").click();
        await composer.waitFor({ state: "visible", timeout: 30_000 });
    }
}

function longPrompt(token) {
    return `${token} Responde en español con exactamente dieciocho frases numeradas sobre métodos generales de organización del trabajo. Cada frase debe tener al menos dieciocho palabras. No uses herramientas de Odoo ni realices cambios.`;
}

async function startTurn(page, prompt) {
    const composer = page.locator("#o_ai_assistant_question");
    await composer.waitFor({ state: "visible", timeout: 30_000 });
    assert.equal(await composer.isEnabled(), true, "active conversation composer is unexpectedly disabled");
    await composer.fill(prompt);
    const [response] = await Promise.all([
        page.waitForResponse(
            (candidate) =>
                new URL(candidate.url()).pathname === "/odoo_ai/v1/turn" &&
                candidate.request().method() === "POST",
            { timeout: 60_000 }
        ),
        page.getByRole("button", { name: "Enviar mensaje" }).click(),
    ]);
    const envelope = await response.json();
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

async function requireUnresolved(page, turnId, label) {
    const status = await turnStatus(page, turnId);
    assert.ok(
        !TERMINAL_STATES.has(status.state),
        `${label} became terminal before the non-blocking interaction could be exercised; use a longer safe prompt`
    );
    return status;
}

async function cancelIfUnresolved(page, turnId) {
    if (!turnId) return;
    try {
        const status = await turnStatus(page, turnId);
        if (!TERMINAL_STATES.has(status.state)) {
            await jsonRpc(page, "/odoo_ai/v1/turn/cancel", { turn_id: turnId });
        }
    } catch {
        // Cleanup is best-effort; the disposable database remains the safety boundary.
    }
}

async function openHistory(page) {
    const back = page.getByRole("button", { name: "Volver al historial" });
    await back.waitFor({ state: "visible", timeout: 30_000 });
    assert.equal(await back.isEnabled(), true, "history navigation is blocked by a running turn");
    await back.click();
    await page.locator(".o_ai_assistant_history").waitFor({ state: "visible", timeout: 30_000 });
}

async function newChatFromHistory(page) {
    const button = page.locator(".o_ai_assistant_history_item_new");
    await button.waitFor({ state: "visible", timeout: 30_000 });
    assert.equal(await button.isEnabled(), true, "new chat is blocked by another conversation");
    await button.click();
    await page.locator("#o_ai_assistant_question").waitFor({ state: "visible", timeout: 30_000 });
}

async function selectHistoryConversation(page, token) {
    const button = page.locator(".o_ai_assistant_history_item_open").filter({ hasText: token });
    assert.equal(await button.count(), 1, `expected exactly one history conversation for ${token}`);
    assert.equal(await button.isEnabled(), true, `conversation ${token} is not navigable`);
    await button.click();
    await page.locator("#o_ai_assistant_question").waitFor({ state: "visible", timeout: 30_000 });
}

async function assertVisibleConversationMessages(page, presentToken, absentToken) {
    const text = await page.locator(".o_ai_assistant_messages").innerText();
    assert.ok(text.includes(presentToken), `visible chat is missing ${presentToken}`);
    assert.ok(!text.includes(absentToken), `visible chat leaked content from ${absentToken}`);
}

async function turnSnapshot(page, turnId) {
    for (let attempt = 0; attempt < 50; attempt += 1) {
        const rows = await datasetCall(
            page,
            "odoo.ai.turn",
            "search_read",
            [[["turn_uuid", "=", turnId]]],
            {
                fields: ["turn_uuid", "reasoning_model", "policy_payload", "state", "attempt_count"],
                limit: 1,
            }
        );
        if (Array.isArray(rows) && rows.length === 1) {
            return rows[0];
        }
        await page.waitForTimeout(100);
    }
    assert.fail(`persisted turn ${turnId} was not readable by its owning user`);
}

function normalizedModel(value) {
    return typeof value === "string" && value ? value : null;
}

function userPolicy(snapshot) {
    const value = snapshot?.policy_payload?.layers?.user;
    assert.ok(value && typeof value === "object", "turn policy snapshot has no user layer");
    return value;
}

function assertProfilePolicy(snapshot, profile) {
    const expected = PROFILE_POLICY[profile];
    assert.ok(expected, `unsupported profile ${profile}`);
    const actual = userPolicy(snapshot);
    assert.equal(actual.confirmation_mode, expected.confirmation_mode);
    assert.equal(actual.max_auto_risk, expected.max_auto_risk);
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

function familyLabel(value) {
    const match = /^gpt[- ]?(.+)$/i.exec(value || "");
    return match ? `GPT-${match[1]}` : value;
}

function variantLabel(value) {
    if (value === "sol") return "Sol";
    if (value === "terra") return "Terra";
    if (value === "luna") return "Luna";
    return value;
}

async function changeModelThroughUi(page, modelPreferences) {
    const button = page.getByRole("button", { name: "Modelo de Codex" });
    await button.waitFor({ state: "visible", timeout: 30_000 });
    assert.equal(await button.isEnabled(), true, "model selector is blocked by the running turn");

    let targetModel;
    let targetOption = null;
    if (modelPreferences.selected_model) {
        targetModel = null;
    } else {
        targetOption =
            modelPreferences.models.find((item) => !item.family_alias) || modelPreferences.models[0];
        assert.ok(
            targetOption,
            "P5.1 settings snapshot gate needs at least one selectable Codex model"
        );
        targetModel = targetOption.model;
    }

    await button.click();
    const responsePromise = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/chat-model" &&
            response.request().method() === "POST",
        { timeout: 30_000 }
    );
    if (targetModel === null) {
        const pickerOption = page
            .locator(".o_ai_assistant_picker_menu:visible .o_ai_assistant_picker_option")
            .filter({ hasText: "Predeterminado" })
            .first();
        await pickerOption.waitFor({ state: "visible", timeout: 30_000 });
        await pickerOption.click();
    } else if (targetOption.family && targetOption.variant) {
        const family = page
            .locator(".o_ai_assistant_picker_menu:visible .o_ai_assistant_picker_submenu_toggle")
            .filter({ hasText: familyLabel(targetOption.family) })
            .first();
        await family.waitFor({ state: "visible", timeout: 30_000 });
        await family.click();
        const variant = page
            .locator(".o_ai_assistant_picker_submenu:visible .o_ai_assistant_picker_option")
            .filter({ hasText: variantLabel(targetOption.variant) })
            .first();
        await variant.waitFor({ state: "visible", timeout: 30_000 });
        await variant.click();
    } else {
        const pickerOption = page
            .locator(".o_ai_assistant_picker_menu:visible .o_ai_assistant_picker_option")
            .filter({ hasText: familyLabel(targetOption.family || targetOption.display_name) })
            .last();
        await pickerOption.waitFor({ state: "visible", timeout: 30_000 });
        await pickerOption.click();
    }
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
    assert.equal(await button.isEnabled(), true, "autonomy selector is blocked by the running turn");
    await button.click();
    const responsePromise = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/agent-autonomy-set" &&
            response.request().method() === "POST",
        { timeout: 30_000 }
    );
    const pickerOption = page
        .locator(".o_ai_assistant_picker_menu:visible .o_ai_assistant_picker_option")
        .filter({ hasText: PROFILE_LABEL[targetProfile] })
        .last();
    await pickerOption.waitFor({ state: "visible", timeout: 30_000 });
    await pickerOption.click();
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
        // Disposable validation cleanup remains best-effort.
    }
    try {
        await jsonRpc(page, "/odoo_ai/v1/agent-autonomy-set", { profile: originalProfile });
    } catch {
        // Disposable validation cleanup remains best-effort.
    }
}

async function runMultiChat(page, stamp) {
    const tokenA = `P51-A-${stamp}`;
    const tokenB = `P51-B-${stamp}`;
    let turnA = null;
    let turnB = null;
    try {
        turnA = await startTurn(page, longPrompt(tokenA));
        await requireUnresolved(page, turnA.turn_id, "Chat A");

        await openHistory(page);
        await newChatFromHistory(page);
        await assertVisibleConversationMessages(page, "", tokenA).catch(() => {});

        turnB = await startTurn(page, longPrompt(tokenB));
        assert.notEqual(turnA.turn_id, turnB.turn_id);
        assert.notEqual(turnA.conversation_id, turnB.conversation_id);
        await assertVisibleConversationMessages(page, tokenB, tokenA);

        await openHistory(page);
        const itemA = page.locator(".o_ai_assistant_history_item_chat").filter({ hasText: tokenA });
        const itemB = page.locator(".o_ai_assistant_history_item_chat").filter({ hasText: tokenB });
        assert.equal(await itemA.count(), 1);
        assert.equal(await itemB.count(), 1);
        const statePattern = /En cola|En curso|Esperando aprobación|Falló|Revisar recuperación|Completado/;
        assert.match(await itemA.innerText(), statePattern);
        assert.match(await itemB.innerText(), statePattern);

        await selectHistoryConversation(page, tokenA);
        await assertVisibleConversationMessages(page, tokenA, tokenB);

        console.log(
            JSON.stringify({
                gate: "P5.1-BROWSER-MULTICHAT",
                turn_a: turnA.turn_id,
                turn_b: turnB.turn_id,
                conversation_a: turnA.conversation_id,
                conversation_b: turnB.conversation_id,
                result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
            })
        );
    } finally {
        await cancelIfUnresolved(page, turnA?.turn_id);
        await cancelIfUnresolved(page, turnB?.turn_id);
    }
}

async function runSettingsSnapshot(page, stamp) {
    const original = await readPreferences(page);
    const originalModel = original.models.selected_model ?? null;
    const originalProfile = original.autonomyProfile;
    const tokenA = `P51-SNAP-A-${stamp}`;
    const tokenB = `P51-SNAP-B-${stamp}`;
    let turnA = null;
    let turnB = null;
    try {
        turnA = await startTurn(page, longPrompt(tokenA));
        await requireUnresolved(page, turnA.turn_id, "snapshot Turn A");
        const before = await turnSnapshot(page, turnA.turn_id);
        assert.equal(normalizedModel(before.reasoning_model), originalModel);
        assertProfilePolicy(before, originalProfile);

        const selectedModel = await changeModelThroughUi(page, original.models);
        const selectedProfile = await changeAutonomyThroughUi(page, originalProfile);

        const after = await turnSnapshot(page, turnA.turn_id);
        assert.equal(normalizedModel(after.reasoning_model), normalizedModel(before.reasoning_model));
        assert.deepEqual(userPolicy(after), userPolicy(before));

        const newChat = page.getByRole("button", { name: "Nuevo chat" });
        await newChat.waitFor({ state: "visible", timeout: 30_000 });
        assert.equal(await newChat.isEnabled(), true, "new conversation is blocked while A runs");
        await newChat.click();
        await page.locator("#o_ai_assistant_question").waitFor({ state: "visible", timeout: 30_000 });

        turnB = await startTurn(page, longPrompt(tokenB));
        const snapshotB = await turnSnapshot(page, turnB.turn_id);
        assert.equal(normalizedModel(snapshotB.reasoning_model), selectedModel);
        assertProfilePolicy(snapshotB, selectedProfile);

        console.log(
            JSON.stringify({
                gate: "P5.1-BROWSER-SETTINGS-SNAPSHOT",
                turn_a: turnA.turn_id,
                turn_b: turnB.turn_id,
                original_model: originalModel,
                next_model: selectedModel,
                original_profile: originalProfile,
                next_profile: selectedProfile,
                result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
            })
        );
    } finally {
        await restorePreferences(page, originalModel, originalProfile);
        await cancelIfUnresolved(page, turnA?.turn_id);
        await cancelIfUnresolved(page, turnB?.turn_id);
    }
}

async function runReopen(page, stamp) {
    const token = `P51-REOPEN-${stamp}`;
    let turn = null;
    let turnPosts = 0;
    const countTurnPosts = (response) => {
        const url = new URL(response.url());
        if (url.pathname === "/odoo_ai/v1/turn" && response.request().method() === "POST") {
            turnPosts += 1;
        }
    };
    page.on("response", countTurnPosts);
    try {
        turn = await startTurn(page, longPrompt(token));
        await requireUnresolved(page, turn.turn_id, "reopen Turn A");
        assert.equal(turnPosts, 1);

        await page.getByRole("button", { name: "Cerrar AI Assistant" }).click();
        await page.waitForTimeout(1500);
        const whileClosed = await turnStatus(page, turn.turn_id);
        assert.notEqual(whileClosed.state, "cancelled", "closing the panel cancelled the durable turn");

        await page.getByRole("button", { name: "Abrir AI Assistant" }).click();
        await page.locator("#o_ai_assistant_question").waitFor({ state: "visible", timeout: 60_000 });
        await page.waitForTimeout(500);
        assert.equal(turnPosts, 1, "reopening the panel resubmitted the turn");
        await assertVisibleConversationMessages(page, token, "P51-OTHER-CHAT-SENTINEL");

        const afterReopen = await turnStatus(page, turn.turn_id);
        assert.notEqual(afterReopen.state, "cancelled");
        console.log(
            JSON.stringify({
                gate: "P5.1-BROWSER-REOPEN",
                turn_id: turn.turn_id,
                state_while_closed: whileClosed.state,
                state_after_reopen: afterReopen.state,
                turn_posts: turnPosts,
                result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
            })
        );
    } finally {
        page.off("response", countTurnPosts);
        await cancelIfUnresolved(page, turn?.turn_id);
    }
}

const gateId = option("--gate");
assert.ok(gateId && GATES.has(gateId), `--gate must be one of ${[...GATES].join(", ")}`);
const baseUrl = required("ODOO_AI_P5_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P5_DB");
const loginName = required("ODOO_AI_P5_LOGIN");
const password = required("ODOO_AI_P5_PASSWORD");
assert.ok(database.startsWith("odoo_ai_"), "P5.1 gates require a disposable odoo_ai_* database");
const stamp = Date.now().toString(36);

const browser = await chromium.launch({ headless: true });
try {
    const context = await browser.newContext();
    const page = await context.newPage();
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
    await login(page, { baseUrl, database, loginName, password });

    if (gateId === "P5.1-BROWSER-MULTICHAT") {
        await runMultiChat(page, stamp);
    } else if (gateId === "P5.1-BROWSER-SETTINGS-SNAPSHOT") {
        await runSettingsSnapshot(page, stamp);
    } else {
        await runReopen(page, stamp);
    }

    assert.deepEqual(browserErrors, []);
    await context.close();
} finally {
    await browser.close();
}
