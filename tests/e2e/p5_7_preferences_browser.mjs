/** Real Chromium P5.7 conversation-preference gates through Odoo and Codex. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const POLICY_GATE = "P5-REAL-SESSION-POLICY";
const LANGUAGE_GATE = "P5-REAL-LANGUAGE-PREFERENCE";
const TERMINAL_STATES = new Set(["completed", "failed", "cancelled", "recovery_required"]);

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

async function callKw(page, model, method, args, kwargs = { context: {} }) {
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
    const runtime = await jsonRpc(page, "/odoo_ai/v1/runtime-account", {});
    assert.equal(
        runtime?.state,
        "authenticated",
        `primary host Codex session is not authenticated: ${runtime?.state || "unknown"}`
    );
}

async function openAssistant(page) {
    const composer = page.locator("#o_ai_assistant_question");
    const history = page.locator(".o_ai_assistant_history");
    if (!(await composer.isVisible()) && !(await history.isVisible())) {
        const launcher = page.locator(".o_ai_assistant_systray button");
        await launcher.waitFor({ state: "visible", timeout: 60_000 });
        await launcher.click();
    }
    await Promise.race([
        composer.waitFor({ state: "visible", timeout: 60_000 }),
        history.waitFor({ state: "visible", timeout: 60_000 }),
    ]);
}

async function newChat(page) {
    if (!(await page.locator(".o_ai_assistant_history").count())) {
        const back = page.locator(".o_ai_assistant_history_button");
        await back.waitFor({ state: "visible", timeout: 30_000 });
        await back.click();
    }
    const button = page.locator(".o_ai_assistant_history_item_new");
    await button.waitFor({ state: "visible", timeout: 30_000 });
    await button.click();
    await page.locator("#o_ai_assistant_question").waitFor({
        state: "visible",
        timeout: 30_000,
    });
}

async function submitTurn(page, prompt) {
    const composer = page.locator("#o_ai_assistant_question");
    await composer.fill(prompt);
    const responsePromise = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/turn" &&
            response.request().method() === "POST",
        { timeout: 60_000 }
    );
    await page.locator(".o_ai_assistant_send_button").click();
    const envelope = await (await responsePromise).json();
    assert.ok(!envelope.error, JSON.stringify(envelope.error));
    assert.equal(envelope.result?.ok, true);
    return envelope.result;
}

async function turnStatus(page, turnId) {
    const status = await jsonRpc(page, "/odoo_ai/v1/turn/status", {
        turn_id: turnId,
        after_sequence: 0,
    });
    assert.equal(status?.ok, true);
    return status;
}

async function waitForDecisionOrTerminal(page, turnId) {
    const deadline = Date.now() + 240_000;
    let status = null;
    while (Date.now() < deadline) {
        status = await turnStatus(page, turnId);
        if (status.state === "awaiting_confirmation" || TERMINAL_STATES.has(status.state)) {
            return status;
        }
        await page.waitForTimeout(500);
    }
    assert.fail(`turn ${turnId} timed out; last state=${status?.state}`);
}

async function waitTerminal(page, turnId) {
    const deadline = Date.now() + 240_000;
    let status = null;
    while (Date.now() < deadline) {
        status = await turnStatus(page, turnId);
        if (TERMINAL_STATES.has(status.state)) return status;
        await page.waitForTimeout(500);
    }
    assert.fail(`turn ${turnId} did not become terminal; last state=${status?.state}`);
}

async function approve(page) {
    const approval = page.locator(".o_ai_assistant_confirmation");
    await approval.waitFor({ state: "visible", timeout: 60_000 });
    const responsePromise = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/turn/plan-decision" &&
            response.request().method() === "POST",
        { timeout: 60_000 }
    );
    await approval.locator("button.btn-primary").click();
    const envelope = await (await responsePromise).json();
    assert.ok(!envelope.error, JSON.stringify(envelope.error));
    assert.equal(envelope.result?.ok, true);
}

async function executePreferenceTurn(page, prompt, capability, { approvalRequired }) {
    const queued = await submitTurn(page, prompt);
    const decision = await waitForDecisionOrTerminal(page, queued.turn_id);
    if (decision.state === "awaiting_confirmation") {
        assert.equal(decision.response?.plan?.steps?.length, 1);
        assert.equal(decision.response.plan.steps[0].capability, capability);
        await approve(page);
    } else {
        assert.equal(approvalRequired, false, `${capability} did not request required approval`);
    }
    const terminal = TERMINAL_STATES.has(decision.state)
        ? decision
        : await waitTerminal(page, queued.turn_id);
    assert.equal(terminal.state, "completed", `${capability} ended in ${terminal.state}`);
    return queued;
}

async function turnRow(page, turnId) {
    const rows = await callKw(
        page,
        "odoo.ai.turn",
        "search_read",
        [[['turn_uuid', '=', turnId]]],
        {
            fields: [
                "turn_uuid",
                "conversation_id",
                "policy_payload",
                "response_language_mode",
                "response_language",
                "conversation_context_payload",
                "working_items_payload",
            ],
            limit: 1,
        }
    );
    assert.equal(rows.length, 1);
    return rows[0];
}

async function conversationRow(page, conversationId) {
    const rows = await callKw(
        page,
        "odoo.ai.conversation",
        "search_read",
        [[['conversation_uuid', '=', conversationId]]],
        {
            fields: ["conversation_uuid", "response_language_mode", "response_language"],
            limit: 1,
        }
    );
    assert.equal(rows.length, 1);
    return rows[0];
}

async function policyRow(page, conversationId) {
    const rows = await callKw(
        page,
        "odoo.ai.chat.policy",
        "search_read",
        [[['conversation_id', '=', conversationId]]],
        {
            fields: [
                "conversation_id",
                "autonomy_override_active",
                "confirmation_mode",
                "max_auto_risk",
            ],
            limit: 1,
        }
    );
    return rows[0] || null;
}

function assertVerifiedCapability(row, capability) {
    const text = JSON.stringify(row.working_items_payload || []);
    assert.ok(text.includes(capability), `${capability} is absent from the durable transcript`);
    assert.ok(text.includes("verified_effect_receipt"), "verified effect receipt is absent");
}

async function runPolicyGate(page) {
    await newChat(page);
    const queued = await submitTurn(
        page,
        "Cambia explícitamente la autonomía sólo de esta conversación al perfil strict para los " +
            "turnos futuros. Usa exactamente assistant.conversation.set_autonomy con profile strict, " +
            "no uses ninguna otra capacidad y espera mi aprobación."
    );
    const pending = await waitForDecisionOrTerminal(page, queued.turn_id);
    assert.equal(pending.state, "awaiting_confirmation");
    assert.equal(pending.response?.plan?.steps?.length, 1);
    assert.equal(
        pending.response.plan.steps[0].capability,
        "assistant.conversation.set_autonomy"
    );
    assert.equal(await policyRow(page, queued.conversation_id), null, "preference changed before approval");
    await approve(page);
    const terminal = await waitTerminal(page, queued.turn_id);
    assert.equal(terminal.state, "completed");

    const policy = await policyRow(page, queued.conversation_id);
    assert.equal(policy?.autonomy_override_active, true);
    assert.equal(policy?.confirmation_mode, "always_confirm");
    assert.equal(policy?.max_auto_risk, "low");
    assertVerifiedCapability(await turnRow(page, queued.turn_id), "assistant.conversation.set_autonomy");

    const future = await submitTurn(
        page,
        "Sin cambiar preferencias ni usar herramientas, responde exactamente P57_POLICY_OK."
    );
    const futureTerminal = await waitTerminal(page, future.turn_id);
    assert.equal(futureTerminal.state, "completed");
    const futureRow = await turnRow(page, future.turn_id);
    const layers = futureRow.policy_payload?.layers;
    assert.equal(layers?.user?.confirmation_mode, "always_confirm");
    assert.equal(layers?.user?.max_auto_risk, "low");
    assert.ok(layers?.administrator && layers?.system_ceiling);

    return {
        gate: POLICY_GATE,
        result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        explicit_approval: true,
        no_preapproval_mutation: true,
        conversation_profile: "strict",
        future_turn_snapshot: "always_confirm/low",
        host_ceiling_present: true,
    };
}

async function runLanguageGate(page) {
    await newChat(page);
    const change = await executePreferenceTurn(
        page,
        "En esta conversación cambia explícitamente el idioma de respuesta para los turnos futuros " +
            "a inglés fijo. Usa exactamente assistant.conversation.set_response_language con mode " +
            "fixed y language en; no uses ninguna otra capacidad.",
        "assistant.conversation.set_response_language",
        { approvalRequired: false }
    );
    const changedConversation = await conversationRow(page, change.conversation_id);
    assert.equal(changedConversation.response_language_mode, "fixed");
    assert.equal(changedConversation.response_language, "en");
    assertVerifiedCapability(
        await turnRow(page, change.turn_id),
        "assistant.conversation.set_response_language"
    );

    const followUp = await submitTurn(
        page,
        "Use one short sentence and reply exactly: THE CURRENT RESPONSE LANGUAGE IS ENGLISH. " +
            "Do not change preferences and do not use tools."
    );
    assert.equal(followUp.conversation_id, change.conversation_id);
    const followTerminal = await waitTerminal(page, followUp.turn_id);
    assert.equal(followTerminal.state, "completed");
    assert.ok(followTerminal.answer?.includes("ENGLISH"));
    const followRow = await turnRow(page, followUp.turn_id);
    assert.equal(followRow.response_language_mode, "fixed");
    assert.equal(followRow.response_language, "en");
    assert.equal(
        followRow.conversation_context_payload?.session_settings?.response_language,
        "en"
    );

    await newChat(page);
    const isolated = await submitTurn(
        page,
        "Responde exactamente AISLAMIENTO_CORRECTO. No cambies preferencias ni uses herramientas."
    );
    assert.notEqual(isolated.conversation_id, change.conversation_id);
    const isolatedTerminal = await waitTerminal(page, isolated.turn_id);
    assert.equal(isolatedTerminal.state, "completed");
    assert.ok(isolatedTerminal.answer?.includes("AISLAMIENTO_CORRECTO"));
    const isolatedConversation = await conversationRow(page, isolated.conversation_id);
    assert.equal(isolatedConversation.response_language_mode, "inherit");
    assert.equal(isolatedConversation.response_language || false, false);
    const isolatedRow = await turnRow(page, isolated.turn_id);
    assert.equal(isolatedRow.response_language_mode, "inherit");
    assert.equal(isolatedRow.response_language || false, false);

    return {
        gate: LANGUAGE_GATE,
        result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        multilingual_switch: "fixed/en",
        neutral_follow_up_preserved: true,
        persisted_turn_snapshot: true,
        second_conversation_isolated: true,
    };
}

const gate = option("--gate");
assert.ok([POLICY_GATE, LANGUAGE_GATE].includes(gate), "unsupported --gate");
const baseUrl = required("ODOO_AI_P5_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P5_DB");
const loginName = required("ODOO_AI_P5_LOGIN");
const password = required("ODOO_AI_P5_PASSWORD");
assert.ok(database.startsWith("odoo_ai_"), "P5.7 gate requires a disposable odoo_ai_* database");

const browser = await chromium.launch({ headless: true });
try {
    const context = await browser.newContext();
    const page = await context.newPage();
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
    await login(page, { baseUrl, database, loginName, password });
    await openAssistant(page);
    const observation =
        gate === POLICY_GATE ? await runPolicyGate(page) : await runLanguageGate(page);
    assert.deepEqual(browserErrors, []);
    console.log(JSON.stringify(observation));
    await context.close();
} finally {
    await browser.close();
}
