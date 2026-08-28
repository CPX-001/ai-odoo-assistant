/** Real Chromium Phase 4 answer-stream gates through persisted Odoo live rows. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const GATES = {
    "P4-REAL-FIRST-DELTA": {
        prompt: "Responde en español con exactamente ocho frases cortas sobre cómo organizar tareas. No uses herramientas de Odoo.",
        cancel: false,
    },
    "P4-REAL-FINAL-PARITY": {
        prompt: "Explica en español, en un párrafo de al menos 180 caracteres, tres ventajas de documentar procesos. No uses herramientas de Odoo.",
        cancel: false,
    },
    "P4-REAL-CANCEL-STREAM": {
        prompt: "Escribe exactamente doce frases sobre métodos generales de planificación, con al menos veinte palabras por frase. No uses herramientas de Odoo.",
        cancel: true,
    },
    "P4-REAL-UTF8-FRAGMENT": {
        prompt: "Responde con un párrafo de al menos 180 caracteres e incluye literalmente esta secuencia: España, pingüino, acción, ñ, 😀. No uses herramientas de Odoo.",
        cancel: false,
    },
};

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
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: rpcParams, id: Date.now() }),
            });
            return response.json();
        },
        { rpcPath: path, rpcParams: params }
    );
    assert.ok(!envelope.error, JSON.stringify(envelope.error));
    return envelope.result;
}

const gateId = option("--gate");
assert.ok(gateId && GATES[gateId], `--gate must be one of ${Object.keys(GATES).join(", ")}`);
const gate = GATES[gateId];
const baseUrl = required("ODOO_AI_P4_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P4_DB");
const login = required("ODOO_AI_P4_LOGIN");
const password = required("ODOO_AI_P4_PASSWORD");
assert.ok(database.startsWith("odoo_ai_"), "Phase 4 gates require a disposable odoo_ai_* database");

const browser = await chromium.launch({ headless: true });
try {
    const context = await browser.newContext();
    const page = await context.newPage();
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));

    await page.goto(`${baseUrl}/web/login?db=${encodeURIComponent(database)}`);
    await page.locator('input[name="login"]').fill(login);
    await page.locator('input[name="password"]').fill(password);
    await Promise.all([
        page.waitForURL((url) => !url.pathname.endsWith("/web/login"), { timeout: 60_000 }),
        page.locator('button[type="submit"]').click(),
    ]);
    await page.goto(`${baseUrl}/web?db=${encodeURIComponent(database)}`);
    await page.getByRole("button", { name: "Abrir AI Assistant" }).click();
    const composer = page.locator("#o_ai_assistant_question");
    await composer.waitFor({ state: "visible", timeout: 60_000 });

    const queuedResponse = page.waitForResponse(
        (response) => new URL(response.url()).pathname === "/odoo_ai/v1/turn" && response.request().method() === "POST",
        { timeout: 60_000 }
    );
    const submitAt = Date.now();
    await composer.fill(gate.prompt);
    await page.getByRole("button", { name: "Enviar mensaje" }).click();
    const queuedEnvelope = await (await queuedResponse).json();
    assert.ok(!queuedEnvelope.error, JSON.stringify(queuedEnvelope.error));
    const queued = queuedEnvelope.result;
    assert.equal(queued?.ok, true);
    assert.equal(typeof queued.turn_id, "string");

    let cursor = 0;
    let firstDeltaAt = null;
    let streamed = "";
    const activityKinds = [];
    let terminal = null;
    let cancelled = false;

    for (let attempt = 0; attempt < 1200; attempt += 1) {
        const live = await jsonRpc(page, "/odoo_ai/v1/turn/live", {
            turn_id: queued.turn_id,
            after_sequence: cursor,
        });
        assert.equal(live?.ok, true);
        assert.equal(live.turn_id, queued.turn_id);
        assert.ok(Array.isArray(live.items));
        for (const item of live.items) {
            assert.ok(item.sequence > cursor, "live cursor must strictly increase");
            cursor = item.sequence;
            if (item.channel === "activity") {
                activityKinds.push(item.event.kind);
                continue;
            }
            assert.equal(item.channel, "answer");
            if (firstDeltaAt === null) {
                firstDeltaAt = Date.now();
            }
            streamed += item.text;
            if (gate.cancel && !cancelled) {
                const cancelledStatus = await jsonRpc(page, "/odoo_ai/v1/turn/cancel", {
                    turn_id: queued.turn_id,
                });
                assert.equal(cancelledStatus?.ok, true);
                cancelled = true;
            }
        }

        terminal = await jsonRpc(page, "/odoo_ai/v1/turn/status", {
            turn_id: queued.turn_id,
            after_sequence: 0,
        });
        assert.equal(terminal?.ok, true);
        if (["completed", "awaiting_confirmation", "failed", "cancelled", "recovery_required"].includes(terminal.state)) {
            break;
        }
        await page.waitForTimeout(100);
    }

    assert.ok(terminal, "turn never reached terminal state");
    assert.ok(firstDeltaAt !== null, "no persisted answer delta observed before terminal state");
    assert.ok(firstDeltaAt >= submitAt);
    assert.ok(activityKinds.includes("agent.answer.started"), "answer start activity missing");
    assert.deepEqual(browserErrors, []);

    if (gate.cancel) {
        assert.equal(cancelled, true, "cancel request was not sent after first delta");
        assert.ok(["cancelled", "failed"].includes(terminal.state), `unexpected cancel terminal state ${terminal.state}`);
        assert.equal(terminal.response ?? null, null, "cancelled stream must not expose stale final response");
    } else {
        assert.ok(["completed", "awaiting_confirmation"].includes(terminal.state));
        const finalAnswer = terminal.response?.answer;
        assert.equal(typeof finalAnswer, "string");
        assert.ok(finalAnswer.length > 0);
        const finalLive = await jsonRpc(page, "/odoo_ai/v1/turn/live", {
            turn_id: queued.turn_id,
            after_sequence: cursor,
        });
        for (const item of finalLive.items || []) {
            cursor = item.sequence;
            if (item.channel === "answer") streamed += item.text;
        }
        assert.equal(streamed, finalAnswer, "provisional answer must reconcile exactly with authoritative final answer");
        assert.ok(!streamed.includes("Analizando petición"));
        assert.ok(!streamed.includes("Consultando datos"));
        const finalMessage = page.locator(".o_ai_assistant_message_assistant .o_ai_assistant_message_content").last();
        await finalMessage.waitFor({ state: "visible", timeout: 30_000 });
        assert.equal((await finalMessage.innerText()).trim(), finalAnswer.trim());
        if (gateId === "P4-REAL-UTF8-FRAGMENT") {
            for (const marker of ["España", "pingüino", "acción", "ñ", "😀"]) {
                assert.ok(streamed.includes(marker), `missing UTF-8 marker ${marker}`);
            }
        }
    }

    console.log(JSON.stringify({
        gate: gateId,
        turn_state: terminal.state,
        first_answer_delta_ms: firstDeltaAt - submitAt,
        streamed_chars: streamed.length,
        activity_kinds: [...new Set(activityKinds)],
        result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
    }));
    await context.close();
} finally {
    await browser.close();
}
