/** Real Chromium P5.6 conversation continuity through the Odoo product path. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const GATE = "P5-REAL-CONTINUITY";
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
    const runtime = await jsonRpc(page, "/odoo_ai/v1/runtime-account", {});
    assert.equal(
        runtime?.state,
        "authenticated",
        `Primary host Codex session is not authenticated: ${runtime?.state || "unknown"}`
    );
    await openAssistant(page);
}

async function openAssistant(page) {
    const open = page.locator(".o_ai_assistant_systray button");
    const composer = page.locator("#o_ai_assistant_question");
    const history = page.locator(".o_ai_assistant_history");
    if (!(await composer.isVisible()) && !(await history.isVisible())) {
        await open.waitFor({ state: "visible", timeout: 60_000 });
        await open.click();
    }
    await Promise.race([
        composer.waitFor({ state: "visible", timeout: 60_000 }),
        history.waitFor({ state: "visible", timeout: 60_000 }),
    ]);
}

async function openHistory(page) {
    if (await page.locator(".o_ai_assistant_history").count()) return;
    const back = page.locator(".o_ai_assistant_history_button");
    await back.waitFor({ state: "visible", timeout: 30_000 });
    await back.click();
    await page.locator(".o_ai_assistant_history").waitFor({ state: "visible", timeout: 30_000 });
}

async function newChat(page) {
    await openHistory(page);
    const button = page.locator(".o_ai_assistant_history_item_new");
    await button.waitFor({ state: "visible", timeout: 30_000 });
    await button.click();
    await page.locator("#o_ai_assistant_question").waitFor({ state: "visible", timeout: 30_000 });
}

async function openConversationByToken(page, token) {
    if (await page.locator("#o_ai_assistant_question").count()) {
        const visible = await page.locator(".o_ai_assistant_messages").innerText().catch(() => "");
        if (visible.includes(token)) return;
    }
    await openHistory(page);
    const item = page.locator(".o_ai_assistant_history_item_open").filter({ hasText: token });
    assert.equal(await item.count(), 1, `expected one conversation containing ${token}`);
    await item.click();
    await page.locator("#o_ai_assistant_question").waitFor({ state: "visible", timeout: 30_000 });
}

async function submitTurn(page, prompt) {
    const composer = page.locator("#o_ai_assistant_question");
    await composer.waitFor({ state: "visible", timeout: 30_000 });
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

async function waitTerminal(page, turnId) {
    const deadline = Date.now() + 180_000;
    let status = null;
    while (Date.now() < deadline) {
        status = await jsonRpc(page, "/odoo_ai/v1/turn/status", {
            turn_id: turnId,
            after_sequence: 0,
        });
        assert.equal(status?.ok, true);
        if (TERMINAL_STATES.has(status.state)) return status;
        await page.waitForTimeout(500);
    }
    assert.fail(`turn ${turnId} did not become terminal; last state=${status?.state}`);
}

async function persistedContext(page, turnId) {
    const rows = await datasetCall(
        page,
        "odoo.ai.turn",
        "search_read",
        [[["turn_uuid", "=", turnId]]],
        {
            fields: ["turn_uuid", "conversation_context_payload"],
            limit: 1,
        }
    );
    assert.equal(rows.length, 1);
    return rows[0].conversation_context_payload;
}

const gateId = option("--gate");
assert.equal(gateId, GATE, `--gate must be ${GATE}`);
const baseUrl = required("ODOO_AI_P5_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P5_DB");
const loginName = required("ODOO_AI_P5_LOGIN");
const password = required("ODOO_AI_P5_PASSWORD");
assert.ok(database.startsWith("odoo_ai_"), "P5.6 gate requires a disposable odoo_ai_* database");

const browser = await chromium.launch({ headless: true });
try {
    const context = await browser.newContext();
    const page = await context.newPage();
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));

    await login(page, { baseUrl, database, loginName, password });
    await newChat(page);

    const token = `P56-CONTEXT-${Date.now().toString(36).toUpperCase()}`;
    const first = await submitTurn(
        page,
        `Guarda para esta conversación la etiqueta exacta ${token}. Responde brevemente confirmando que la has leído. No uses herramientas de Odoo.`
    );
    const firstTerminal = await waitTerminal(page, first.turn_id);
    assert.equal(firstTerminal.state, "completed", `first continuity turn ended in ${firstTerminal.state}`);

    // Reconnect the browser before the follow-up. The provider is also ephemeral per
    // decision, so the exact token must come from Odoo-owned conversation context.
    await page.reload({ waitUntil: "domcontentloaded" });
    await openAssistant(page);
    await openConversationByToken(page, token);

    const second = await submitTurn(
        page,
        "¿Cuál es la etiqueta exacta que te di en mi mensaje anterior? Responde únicamente con esa etiqueta y no uses herramientas."
    );
    assert.equal(second.conversation_id, first.conversation_id);
    const secondTerminal = await waitTerminal(page, second.turn_id);
    assert.equal(secondTerminal.state, "completed", `follow-up ended in ${secondTerminal.state}`);
    assert.ok(
        secondTerminal.answer?.includes(token),
        "follow-up did not recover the exact prior-turn token"
    );

    const snapshot = await persistedContext(page, second.turn_id);
    assert.equal(snapshot?.format_version, 1);
    assert.equal(snapshot?.conversation_id, first.conversation_id);
    const contextText = JSON.stringify(snapshot);
    assert.ok(contextText.includes(token), "persisted turn context omitted the prior token");
    assert.ok(
        !contextText.includes("¿Cuál es la etiqueta exacta"),
        "current user message leaked into its own prior conversation context"
    );

    await newChat(page);
    const isolated = await submitTurn(
        page,
        "Si esta conversación no contiene una etiqueta previa, responde exactamente NO_CONTEXT. No inventes ninguna etiqueta y no uses herramientas."
    );
    assert.notEqual(isolated.conversation_id, first.conversation_id);
    const isolatedTerminal = await waitTerminal(page, isolated.turn_id);
    assert.equal(isolatedTerminal.state, "completed");
    assert.ok(
        !isolatedTerminal.answer?.includes(token),
        "conversation context leaked across conversations"
    );
    assert.ok(
        isolatedTerminal.answer?.includes("NO_CONTEXT"),
        "fresh conversation did not behave as context-isolated"
    );

    assert.deepEqual(browserErrors, []);
    console.log(
        JSON.stringify({
            gate: GATE,
            result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
            reconnect_follow_up: true,
            exact_prior_token_recovered: true,
            persisted_context_version: snapshot.format_version,
            current_message_excluded: true,
            cross_conversation_isolation: true,
        })
    );
    await context.close();
} finally {
    await browser.close();
}
