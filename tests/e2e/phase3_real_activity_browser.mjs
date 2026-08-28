/** Real Chromium Phase 3 public-activity gates through the Odoo-native turn path. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const GATES = {
    "P3-REAL-ACTIVITY-READ": {
        prompt: "Busca en Odoo hasta tres contactos visibles y resume únicamente sus nombres. Usa las capacidades de Odoo necesarias.",
        requiredKinds: ["capability.started"],
        action: false,
        requirePreFinal: false,
    },
    "P3-REAL-ACTIVITY-ACTION": {
        promptEnv: "ODOO_AI_P3_ACTION_PROMPT",
        requiredKinds: ["preview.started", "execution.started", "verification.started"],
        action: true,
        requirePreFinal: false,
    },
    "P3-REAL-LIVE-VISIBILITY": {
        prompt: "Busca en Odoo hasta diez contactos visibles y resume sus nombres. Usa las capacidades de Odoo necesarias.",
        requiredKinds: ["capability.started"],
        action: false,
        requirePreFinal: true,
    },
    "P3-REAL-REDACTION": {
        prompt: "Consulta en Odoo hasta tres contactos visibles y resume sus nombres. Usa las capacidades de Odoo necesarias.",
        requiredKinds: ["capability.started"],
        action: false,
        requirePreFinal: false,
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

const gateId = option("--gate");
assert.ok(gateId && GATES[gateId], `--gate must be one of ${Object.keys(GATES).join(", ")}`);
const gate = GATES[gateId];
const baseUrl = required("ODOO_AI_P3_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P3_DB");
const login = required("ODOO_AI_P3_LOGIN");
const password = required("ODOO_AI_P3_PASSWORD");
assert.ok(database.startsWith("odoo_ai_"), "Phase 3 gates require a disposable odoo_ai_* database");
const prompt = gate.promptEnv ? required(gate.promptEnv) : gate.prompt;
assert.ok(typeof prompt === "string" && prompt.length > 0 && prompt.length <= 4000);

const forbidden = [
    "authorization",
    "password",
    "prompt",
    "reasoning",
    "stderr",
    "stdout",
    "token",
    "working_items",
    "arguments_json",
    "result_payload",
    "chain-of-thought",
];

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
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/turn" &&
            response.request().method() === "POST",
        { timeout: 60_000 }
    );
    await composer.fill(prompt);
    await page.getByRole("button", { name: "Enviar mensaje" }).click();
    const queuedEnvelope = await (await queuedResponse).json();
    assert.ok(!queuedEnvelope.error, JSON.stringify(queuedEnvelope.error));
    const queued = queuedEnvelope.result;
    assert.equal(queued?.ok, true);
    assert.equal(typeof queued.turn_id, "string");

    const activitySurface = page.locator(".o_ai_assistant_activity").last();
    await activitySurface.waitFor({ state: "visible", timeout: 120_000 });

    if (gate.requirePreFinal) {
        const whileVisible = await jsonRpc(page, "/odoo_ai/v1/turn/status", {
            turn_id: queued.turn_id,
            after_sequence: 0,
        });
        assert.equal(whileVisible?.ok, true);
        assert.ok(
            !["completed", "awaiting_confirmation", "failed", "cancelled", "recovery_required"].includes(whileVisible.state),
            `activity was not observed before terminal completion; state=${whileVisible.state}`
        );
    }

    if (gate.action) {
        const continueButton = page.getByRole("button", { name: "Continuar" });
        await continueButton.waitFor({ state: "visible", timeout: 120_000 });
        await continueButton.click();
    }

    let cursor = 0;
    const events = [];
    let terminal = null;
    for (let attempt = 0; attempt < 1200; attempt += 1) {
        const live = await jsonRpc(page, "/odoo_ai/v1/turn/live", {
            turn_id: queued.turn_id,
            after_sequence: cursor,
        });
        assert.equal(live?.ok, true);
        assert.equal(live.turn_id, queued.turn_id);
        for (const item of live.items || []) {
            assert.ok(item.sequence > cursor, "live event order must be strictly increasing");
            cursor = item.sequence;
            if (item.channel === "activity") {
                events.push(item.event);
            }
        }

        terminal = await jsonRpc(page, "/odoo_ai/v1/turn/status", {
            turn_id: queued.turn_id,
            after_sequence: 0,
        });
        assert.equal(terminal?.ok, true);
        if (["completed", "awaiting_confirmation", "failed", "cancelled", "recovery_required"].includes(terminal.state)) {
            if (!gate.action || ["completed", "failed", "recovery_required"].includes(terminal.state)) {
                break;
            }
        }
        await page.waitForTimeout(100);
    }

    assert.ok(terminal, "turn never reached an expected terminal state");
    const kinds = new Set(events.map((event) => event.kind));
    for (const kind of gate.requiredKinds) {
        assert.ok(kinds.has(kind), `missing public activity kind ${kind}; got ${[...kinds].join(", ")}`);
    }
    assert.ok(!kinds.has("agent.thinking"), "private reasoning kind was exposed");

    const activityText = (await activitySurface.innerText()).toLowerCase();
    const encodedEvents = JSON.stringify(events).toLowerCase();
    for (const secret of forbidden) {
        assert.ok(!activityText.includes(secret), `activity UI leaked forbidden marker ${secret}`);
        assert.ok(!encodedEvents.includes(`\"${secret}\"`), `public event leaked forbidden field ${secret}`);
    }
    for (const event of events) {
        assert.ok(!Object.prototype.hasOwnProperty.call(event, "payload"), "arbitrary payload field exposed");
    }
    assert.deepEqual(browserErrors, []);

    console.log(
        JSON.stringify({
            gate: gateId,
            turn_state: terminal.state,
            public_event_count: events.length,
            public_kinds: [...kinds],
            pre_final_visibility_checked: gate.requirePreFinal,
            result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        })
    );
    await context.close();
} finally {
    await browser.close();
}
