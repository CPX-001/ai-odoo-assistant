/** Real Chromium P5.4 final activity/answer UX through the Odoo product path. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const GATE = "P5-REAL-CHAT-BASIC";
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

async function ensureNewChat(page) {
    const button = page.getByRole("button", { name: "Nuevo chat" });
    if (await button.count()) {
        await button.click();
        await page.locator("#o_ai_assistant_question").waitFor({ state: "visible", timeout: 30_000 });
    }
}

function longPrompt(token) {
    return `${token} Responde en español con exactamente veinte frases numeradas sobre métodos generales de organización del trabajo. Cada frase debe tener al menos dieciocho palabras. No uses herramientas de Odoo ni realices cambios.`;
}

async function submitTurn(page, prompt, token) {
    const composer = page.locator("#o_ai_assistant_question");
    await composer.fill(prompt);
    const responsePromise = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/turn" &&
            response.request().method() === "POST",
        { timeout: 60_000 }
    );
    const submittedAt = Date.now();
    await page.getByRole("button", { name: "Enviar mensaje" }).click();

    const userMessage = page.locator(".o_ai_assistant_message_user").filter({ hasText: token });
    await userMessage.waitFor({ state: "visible", timeout: 2_000 });
    const userRenderMs = Date.now() - submittedAt;
    assert.ok(userRenderMs < 2_000, `user message took ${userRenderMs}ms to render`);

    const envelope = await (await responsePromise).json();
    assert.ok(!envelope.error, JSON.stringify(envelope.error));
    assert.equal(envelope.result?.ok, true);
    assert.equal(typeof envelope.result.turn_id, "string");
    return { queued: envelope.result, userRenderMs };
}

async function waitForActivity(page) {
    const activity = page.locator(".o_ai_assistant_activity");
    await activity.waitFor({ state: "visible", timeout: 45_000 });
    const nestedInAssistantBubble = await activity.evaluate(
        (node) => Boolean(node.closest(".o_ai_assistant_message_assistant"))
    );
    assert.equal(nestedInAssistantBubble, false, "public activity leaked into Assistant prose bubble");
    assert.equal(
        await page.getByText("Pensando…", { exact: true }).count(),
        0,
        "fake Pensando bubble was visible while real activity existed"
    );
    return true;
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

const gateId = option("--gate");
assert.equal(gateId, GATE, `--gate must be ${GATE}`);
const baseUrl = required("ODOO_AI_P5_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P5_DB");
const loginName = required("ODOO_AI_P5_LOGIN");
const password = required("ODOO_AI_P5_PASSWORD");
assert.ok(database.startsWith("odoo_ai_"), "P5.4 gate requires a disposable odoo_ai_* database");

const browser = await chromium.launch({ headless: true });
try {
    const context = await browser.newContext();
    const page = await context.newPage();
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));

    await login(page, { baseUrl, database, loginName, password });
    await ensureNewChat(page);

    const token = `P54-BASIC-${Date.now().toString(36)}`;
    const { queued, userRenderMs } = await submitTurn(page, longPrompt(token), token);

    const observedActivity = await waitForActivity(page);
    const terminal = await waitTerminal(page, queued.turn_id);
    assert.equal(terminal.state, "completed", `basic chat ended in ${terminal.state}`);

    await page.waitForFunction(
        () => document.querySelectorAll(".o_ai_assistant_turn_status").length === 0,
        null,
        { timeout: 30_000 }
    );
    await page.waitForTimeout(250);

    const finalAssistantMessages = page.locator(".o_ai_assistant_message_assistant");
    assert.equal(
        await finalAssistantMessages.count(),
        1,
        "one turn rendered more than one final Assistant message"
    );
    const finalText = (await finalAssistantMessages.first().innerText()).trim();
    assert.ok(finalText && !finalText.includes("Pensando…"), "final Assistant message is empty/fallback");

    const settledActivity = page.locator(".o_ai_assistant_activity_settled");
    assert.ok(await settledActivity.count(), "activity did not settle separately from the final answer");
    assert.equal(await page.getByText("Pensando…", { exact: true }).count(), 0);
    assert.deepEqual(browserErrors, []);

    console.log(
        JSON.stringify({
            gate: GATE,
            result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
            user_message_render_ms: userRenderMs,
            public_activity_observed: observedActivity,
            activity_separate_from_answer: true,
            final_assistant_message_count: 1,
            fake_thinking_visible_with_activity: false,
        })
    );

    await context.close();
} finally {
    await browser.close();
}
