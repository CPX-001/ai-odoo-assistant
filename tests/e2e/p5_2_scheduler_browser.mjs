/** Real Chromium validation for P5.2 scheduler concurrency, ordering and backpressure. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const GATES = new Set([
    "P5-REAL-MULTICHAT",
    "P5-REAL-CONVERSATION-ORDERING",
    "P5-REAL-BACKPRESSURE",
]);
const TERMINAL = new Set(["completed", "failed", "cancelled", "recovery_required"]);
const CAPACITY_KEY = "odoo_ai_assistant.concurrent_turns";
let requestSequence = 0;

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
}

function screen() {
    return {
        action_id: null,
        allowed_context_subset: {},
        captured_at: new Date().toISOString(),
        menu_id: null,
        model: null,
        res_id: null,
        selected_ids: [],
        view_type: null,
    };
}

function longPrompt(token) {
    return `${token} Responde en español con cuarenta puntos numerados sobre organización general del trabajo. Cada punto debe tener al menos treinta palabras. No consultes datos de Odoo, no uses herramientas y no realices cambios.`;
}

async function enqueue(page, message, conversationId = null) {
    requestSequence += 1;
    const result = await jsonRpc(page, "/odoo_ai/v1/turn", {
        message,
        screen: screen(),
        conversation_id: conversationId,
        client_request_id: `p52.${Date.now()}.${requestSequence}`,
    });
    assert.equal(result?.ok, true, JSON.stringify(result));
    assert.equal(typeof result.turn_id, "string");
    assert.equal(typeof result.conversation_id, "string");
    return result;
}

async function status(page, turnId) {
    const result = await jsonRpc(page, "/odoo_ai/v1/turn/status", {
        turn_id: turnId,
        after_sequence: 0,
    });
    assert.equal(result?.ok, true, JSON.stringify(result));
    return result;
}

async function snapshot(page) {
    const result = await datasetCall(
        page,
        "odoo.ai.assistant.diagnostics",
        "assistant_scheduler_snapshot"
    );
    assert.equal(typeof result?.effective_capacity, "number");
    assert.equal(typeof result?.active_count, "number");
    return result;
}

async function setCapacity(page, value) {
    await datasetCall(page, "ir.config_parameter", "set_param", [CAPACITY_KEY, String(value)]);
    const result = await snapshot(page);
    assert.equal(result.effective_capacity, value);
}

async function getRawCapacity(page) {
    return datasetCall(page, "ir.config_parameter", "get_param", [CAPACITY_KEY, ""]);
}

async function restoreCapacity(page, raw) {
    if (raw === "" || raw === false || raw === null || raw === undefined) {
        await datasetCall(page, "ir.config_parameter", "set_param", [CAPACITY_KEY, "2"]);
    } else {
        await datasetCall(page, "ir.config_parameter", "set_param", [CAPACITY_KEY, String(raw)]);
    }
}

async function waitFor(page, description, probe, timeoutMs = 60_000) {
    const deadline = Date.now() + timeoutMs;
    let last;
    while (Date.now() < deadline) {
        last = await probe();
        if (last?.ok) return last.value;
        await page.waitForTimeout(150);
    }
    assert.fail(`${description} timed out; last=${JSON.stringify(last)}`);
}

async function waitForState(page, turnId, expected, timeoutMs = 60_000) {
    return waitFor(
        page,
        `${turnId} -> ${expected}`,
        async () => {
            const current = await status(page, turnId);
            if (current.state === expected) return { ok: true, value: current };
            if (TERMINAL.has(current.state) && !TERMINAL.has(expected)) {
                assert.fail(`${turnId} became ${current.state} before reaching ${expected}`);
            }
            return { ok: false, state: current.state };
        },
        timeoutMs
    );
}

async function waitUntilNotQueued(page, turnId, timeoutMs = 20_000) {
    return waitFor(
        page,
        `${turnId} to leave queued`,
        async () => {
            const current = await status(page, turnId);
            return current.state !== "queued"
                ? { ok: true, value: current }
                : { ok: false, state: current.state };
        },
        timeoutMs
    );
}

async function waitTerminal(page, turnId, timeoutMs = 60_000) {
    return waitFor(
        page,
        `${turnId} terminal`,
        async () => {
            const current = await status(page, turnId);
            return TERMINAL.has(current.state)
                ? { ok: true, value: current }
                : { ok: false, state: current.state };
        },
        timeoutMs
    );
}

async function cancelIfUnresolved(page, turnId) {
    if (!turnId) return;
    try {
        const current = await status(page, turnId);
        if (!TERMINAL.has(current.state)) {
            await jsonRpc(page, "/odoo_ai/v1/turn/cancel", { turn_id: turnId });
        }
    } catch {
        // Disposable database is the final cleanup boundary.
    }
}

async function runMultiChat(page, stamp) {
    const originalCapacity = await getRawCapacity(page);
    let first;
    let second;
    try {
        await setCapacity(page, 2);
        first = await enqueue(page, longPrompt(`P52-MULTI-A-${stamp}`));
        second = await enqueue(page, longPrompt(`P52-MULTI-B-${stamp}`));
        assert.notEqual(first.conversation_id, second.conversation_id);

        let peak = 0;
        await waitFor(
            page,
            "two independent conversations to overlap",
            async () => {
                const [a, b, scheduler] = await Promise.all([
                    status(page, first.turn_id),
                    status(page, second.turn_id),
                    snapshot(page),
                ]);
                peak = Math.max(peak, scheduler.active_count);
                assert.ok(scheduler.active_count <= 2, "scheduler exceeded capacity=2");
                if (a.state === "running" && b.state === "running") {
                    return { ok: true, value: { a, b, scheduler } };
                }
                if (TERMINAL.has(a.state) || TERMINAL.has(b.state)) {
                    assert.fail("a long read-only turn finished before concurrency overlap was observed");
                }
                return { ok: false, a: a.state, b: b.state, scheduler };
            },
            45_000
        );
        assert.equal(peak, 2);
        console.log(JSON.stringify({
            gate: "P5-REAL-MULTICHAT",
            effective_capacity: 2,
            peak_active: peak,
            result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        }));
    } finally {
        await cancelIfUnresolved(page, first?.turn_id);
        await cancelIfUnresolved(page, second?.turn_id);
        await restoreCapacity(page, originalCapacity);
    }
}

async function runConversationOrdering(page, stamp) {
    const originalCapacity = await getRawCapacity(page);
    let first;
    let second;
    try {
        await setCapacity(page, 2);
        first = await enqueue(page, longPrompt(`P52-ORDER-A-${stamp}`));
        await waitForState(page, first.turn_id, "running");
        second = await enqueue(
            page,
            longPrompt(`P52-ORDER-B-${stamp}`),
            first.conversation_id
        );

        for (let index = 0; index < 8; index += 1) {
            const [firstState, secondState, scheduler] = await Promise.all([
                status(page, first.turn_id),
                status(page, second.turn_id),
                snapshot(page),
            ]);
            assert.ok(!TERMINAL.has(firstState.state), "predecessor finished before ordering was exercised");
            assert.equal(secondState.state, "queued", "later same-conversation turn overtook predecessor");
            assert.ok(scheduler.causally_blocked_count >= 1);
            await page.waitForTimeout(200);
        }

        await jsonRpc(page, "/odoo_ai/v1/turn/cancel", { turn_id: first.turn_id });
        await waitTerminal(page, first.turn_id);
        const released = await waitUntilNotQueued(page, second.turn_id, 20_000);
        assert.ok(
            ["running", "completed", "failed", "cancelled", "recovery_required"].includes(released.state),
            `unexpected released state ${released.state}`
        );
        console.log(JSON.stringify({
            gate: "P5-REAL-CONVERSATION-ORDERING",
            predecessor: first.turn_id,
            successor: second.turn_id,
            successor_after_release: released.state,
            result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        }));
    } finally {
        await cancelIfUnresolved(page, first?.turn_id);
        await cancelIfUnresolved(page, second?.turn_id);
        await restoreCapacity(page, originalCapacity);
    }
}

async function runBackpressure(page, stamp) {
    const originalCapacity = await getRawCapacity(page);
    let first;
    let second;
    try {
        await setCapacity(page, 1);
        first = await enqueue(page, longPrompt(`P52-BACK-A-${stamp}`));
        await waitForState(page, first.turn_id, "running");
        second = await enqueue(page, longPrompt(`P52-BACK-B-${stamp}`));

        for (let index = 0; index < 8; index += 1) {
            const [firstState, secondState, scheduler] = await Promise.all([
                status(page, first.turn_id),
                status(page, second.turn_id),
                snapshot(page),
            ]);
            assert.ok(!TERMINAL.has(firstState.state), "capacity holder finished before backpressure was observed");
            assert.equal(secondState.state, "queued", "excess work did not remain queued");
            assert.ok(scheduler.active_count <= 1, "scheduler exceeded capacity=1");
            assert.ok(scheduler.queued_count >= 1);
            await page.waitForTimeout(200);
        }

        const releasedAt = Date.now();
        await jsonRpc(page, "/odoo_ai/v1/turn/cancel", { turn_id: first.turn_id });
        await waitTerminal(page, first.turn_id);
        const secondAfterRelease = await waitUntilNotQueued(page, second.turn_id, 20_000);
        const wakeDelayMs = Date.now() - releasedAt;
        assert.ok(wakeDelayMs < 20_000, "pending turn relied on the minute cron instead of release wake-up");
        console.log(JSON.stringify({
            gate: "P5-REAL-BACKPRESSURE",
            effective_capacity: 1,
            successor_after_release: secondAfterRelease.state,
            wake_delay_ms: wakeDelayMs,
            result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        }));
    } finally {
        await cancelIfUnresolved(page, first?.turn_id);
        await cancelIfUnresolved(page, second?.turn_id);
        await restoreCapacity(page, originalCapacity);
    }
}

const gate = option("--gate");
assert.ok(GATES.has(gate), `--gate must be one of ${[...GATES].join(", ")}`);
const baseUrl = required("ODOO_AI_P5_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P5_DB");
const loginName = required("ODOO_AI_P5_LOGIN");
const password = required("ODOO_AI_P5_PASSWORD");
assert.ok(database.startsWith("odoo_ai_"), "P5.2 real gates require a disposable odoo_ai_* database");

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
const stamp = `${Date.now()}`;
try {
    await login(page, { baseUrl, database, loginName, password });
    if (gate === "P5-REAL-MULTICHAT") await runMultiChat(page, stamp);
    if (gate === "P5-REAL-CONVERSATION-ORDERING") await runConversationOrdering(page, stamp);
    if (gate === "P5-REAL-BACKPRESSURE") await runBackpressure(page, stamp);
} finally {
    await context.close();
    await browser.close();
}
