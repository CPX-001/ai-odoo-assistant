/** Real Chromium P5.5 post-effect reasoning acceptance through the current Odoo-native path. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const GATE = "P5-REAL-POST-EFFECT";
const TERMINAL_STATES = new Set(["completed", "failed", "cancelled", "recovery_required"]);
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

function positiveInteger(name) {
    const value = Number(required(name));
    assert.ok(Number.isSafeInteger(value) && value > 0, `${name} must be a positive integer`);
    return value;
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
}

async function selectAutonomy(page, label) {
    const picker = page.getByRole("button", { name: "Nivel de autonomía del Assistant" });
    await picker.waitFor({ state: "visible", timeout: 30_000 });
    await picker.click();
    await page.getByText(label, { exact: true }).last().click();
    await page.waitForFunction(
        (expected) =>
            document.querySelector('button[aria-label="Nivel de autonomía del Assistant"]')?.title
            === expected,
        `Autonomía: ${label}`,
        { timeout: 30_000 }
    );
}

async function readAutonomyProfile(page) {
    const result = await jsonRpc(page, "/odoo_ai/v1/agent-autonomy", {});
    assert.equal(result?.ok, true);
    assert.ok(PROFILE_LABEL[result.profile], `unsupported autonomy profile ${result?.profile}`);
    return result.profile;
}

async function readReference(page, recordId) {
    const rows = await callKw(page, "res.partner", "read", [[recordId], ["ref"]]);
    assert.equal(rows.length, 1);
    return rows[0].ref || "";
}

async function waitForReference(page, recordId, expected) {
    const deadline = Date.now() + 180_000;
    while (Date.now() < deadline) {
        if ((await readReference(page, recordId)) === expected) return;
        await page.waitForTimeout(500);
    }
    assert.fail("verified P5.5 fixture value was not observed before timeout");
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

async function turnRow(page, turnId) {
    const rows = await callKw(
        page,
        "odoo.ai.turn",
        "search_read",
        [[["turn_uuid", "=", turnId]]],
        {
            fields: [
                "turn_uuid",
                "state",
                "write_barrier",
                "working_items_payload",
                "capability_plan_payload",
                "result_payload",
            ],
            limit: 1,
        }
    );
    assert.ok(Array.isArray(rows) && rows.length === 1, "own P5.5 turn row is not readable");
    return rows[0];
}

function assertPostEffectTranscript(row, finalMarker) {
    const items = row.working_items_payload;
    assert.ok(Array.isArray(items) && items.length > 0, "turn has no durable working transcript");
    const receipts = items.filter((item) => item?.kind === "verified_effect_receipt");
    assert.equal(receipts.length, 1, "turn must contain exactly one verified effect receipt");
    const receiptIndex = items.findIndex((item) => item?.kind === "verified_effect_receipt");
    const finalIndexes = items
        .map((item, index) => (item?.kind === "final_answer" ? index : -1))
        .filter((index) => index >= 0);
    assert.equal(finalIndexes.length, 1, "turn must contain exactly one final_answer working item");
    assert.ok(finalIndexes[0] > receiptIndex, "final_answer was not produced after verified receipt");
    const finalItem = items[finalIndexes[0]];
    assert.ok(
        typeof finalItem?.data?.answer === "string" && finalItem.data.answer.includes(finalMarker),
        "post-effect provider final answer omitted the requested marker"
    );
    const executableProposalsAfterReceipt = items
        .slice(receiptIndex + 1)
        .filter((item) => item?.kind === "plan_step_proposed");
    assert.equal(
        executableProposalsAfterReceipt.length,
        0,
        "a second effect proposal entered the executable transcript after verification"
    );
    const rejectedPostEffectPlans = items
        .slice(receiptIndex + 1)
        .filter(
            (item) =>
                item?.kind === "capability_error" &&
                item?.data?.code === "agent_plan_capability_not_allowed"
        ).length;
    return {
        itemCount: items.length,
        rejectedPostEffectPlans,
    };
}

const gateId = option("--gate");
assert.equal(gateId, GATE, `--gate must be ${GATE}`);
const baseUrl = required("ODOO_AI_P5_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P5_DB");
const loginName = required("ODOO_AI_P5_LOGIN");
const password = required("ODOO_AI_P5_PASSWORD");
const actionId = positiveInteger("ODOO_AI_P5_APPROVAL_ACTION_ID");
assert.ok(database.startsWith("odoo_ai_"), "P5.5 gate requires a disposable odoo_ai_* database");

const browser = await chromium.launch({ headless: true });
let context = null;
let page = null;
let fixtureId = null;
let originalProfile = null;
let fixtureDeleted = false;
try {
    context = await browser.newContext();
    page = await context.newPage();
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));

    await login(page, { baseUrl, database, loginName, password });
    originalProfile = await readAutonomyProfile(page);

    const token = Date.now().toString(36).toUpperCase();
    const before = `P55-BASE-${token}`;
    const proposed = `P55-EFFECT-${token}`;
    const finalMarker = `P55-FINAL-${token}`;
    fixtureId = await callKw(page, "res.partner", "create", [
        { name: `P5.5 disposable post-effect fixture ${token}`, ref: before },
    ]);
    assert.ok(Number.isSafeInteger(fixtureId) && fixtureId > 0, "failed to create P5.5 fixture record");

    await page.goto(
        `${baseUrl}/web#id=${fixtureId}&action=${actionId}`
        + "&model=res.partner&view_type=form"
    );
    await page.locator(".o_form_view").waitFor({ state: "visible", timeout: 60_000 });
    await page.getByRole("button", { name: "Abrir AI Assistant" }).click();
    await page.getByText(`res.partner #${fixtureId}`, { exact: true }).waitFor();
    const newChat = page.getByRole("button", { name: "Nuevo chat" });
    if (await newChat.count()) await newChat.click();
    await selectAutonomy(page, "Estricto");

    const composer = page.locator("#o_ai_assistant_question");
    const queuedResponse = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/turn" &&
            response.request().method() === "POST",
        { timeout: 60_000 }
    );
    await composer.fill(
        `En el registro actual cambia únicamente el campo ref al valor ${proposed}. `
        + "Prepara exactamente una propuesta con odoo.record.patch y espera mi aprobación; "
        + "no ejecutes ni afirmes éxito antes de aprobar. Después de ejecutar y verificar el cambio, "
        + `continúa razonando desde el resultado verificado y responde en español incluyendo literalmente ${finalMarker}. `
        + "No propongas ni ejecutes una segunda modificación después de verificar."
    );
    await page.getByRole("button", { name: "Enviar mensaje" }).click();
    const queuedEnvelope = await (await queuedResponse).json();
    assert.ok(!queuedEnvelope.error, JSON.stringify(queuedEnvelope.error));
    const queued = queuedEnvelope.result;
    assert.equal(queued?.ok, true);
    assert.equal(typeof queued.turn_id, "string");

    const approval = page.locator(".o_ai_assistant_confirmation");
    await approval.waitFor({ state: "visible", timeout: 180_000 });
    assert.equal(await readReference(page, fixtureId), before, "business write happened before approval");

    const pending = await turnStatus(page, queued.turn_id);
    assert.equal(pending.state, "awaiting_confirmation");
    assert.equal(pending.response?.plan?.state, "awaiting_confirmation");
    assert.equal(pending.response?.plan?.steps?.length, 1);
    assert.equal(pending.response.plan.steps[0].capability, "odoo.record.patch");

    const decisionResponse = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/turn/plan-decision" &&
            response.request().method() === "POST",
        { timeout: 60_000 }
    );
    await approval.getByRole("button", { name: "Continuar" }).click();
    const decisionEnvelope = await (await decisionResponse).json();
    assert.ok(!decisionEnvelope.error, JSON.stringify(decisionEnvelope.error));
    assert.equal(decisionEnvelope.result?.ok, true);
    assert.equal(decisionEnvelope.result?.plan_id, queued.turn_id);
    assert.equal(decisionEnvelope.result?.state, "authorized");

    await waitForReference(page, fixtureId, proposed);
    const terminal = await waitTerminal(page, queued.turn_id);
    assert.equal(terminal.state, "completed", `post-effect turn ended in ${terminal.state}`);
    assert.equal(terminal.response?.plan?.state, "completed");
    assert.equal(terminal.response?.plan?.steps?.length, 1);
    assert.equal(terminal.response.plan.steps[0].capability, "odoo.record.patch");
    assert.equal(terminal.response.plan.steps[0].receipt?.outcome, "verified");
    assert.ok(
        typeof terminal.response?.answer === "string" && terminal.response.answer.includes(finalMarker),
        "terminal response is not the requested post-effect provider synthesis"
    );
    assert.ok(
        !terminal.response.answer.startsWith("He completado y verificado la acción:") &&
        terminal.response.answer !== "He completado y verificado las acciones solicitadas.",
        "terminal response fell back to deterministic host completion prose"
    );

    const row = await turnRow(page, queued.turn_id);
    assert.equal(row.state, "completed");
    assert.equal(row.write_barrier, true, "effect completed without the durable write barrier");
    assert.equal(row.capability_plan_payload?.plan?.state, "completed");
    assert.equal(row.capability_plan_payload?.plan?.steps?.length, 1);
    assert.equal(row.result_payload?.plan?.state, "completed");
    assert.equal(row.result_payload?.plan?.steps?.length, 1);
    assert.ok(row.capability_plan_payload.plan.steps[0].result);
    assert.ok(row.capability_plan_payload.plan.steps[0].verification);
    const transcript = assertPostEffectTranscript(row, finalMarker);

    await page.waitForFunction(
        (marker) =>
            Array.from(document.querySelectorAll(".o_ai_assistant_message_assistant"))
                .some((node) => node.textContent?.includes(marker)),
        finalMarker,
        { timeout: 60_000 }
    );
    const assistantMessages = page.locator(".o_ai_assistant_message_assistant");
    assert.equal(await assistantMessages.count(), 1, "one effectful turn rendered duplicate Assistant finals");
    assert.ok((await assistantMessages.first().innerText()).includes(finalMarker));
    assert.equal(await readReference(page, fixtureId), proposed);
    assert.deepEqual(browserErrors, []);

    console.log(JSON.stringify({
        gate: GATE,
        result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        approval_required_before_write: true,
        write_barrier_observed: true,
        verified_effect_receipt_count: 1,
        completed_effect_steps: 1,
        post_effect_final_answer_observed: true,
        final_marker_observed: true,
        deterministic_completion_fallback_observed: false,
        executable_plan_proposals_after_receipt: 0,
        rejected_post_effect_plan_attempts: transcript.rejectedPostEffectPlans,
        durable_working_item_count: transcript.itemCount,
        final_assistant_message_count: 1,
    }));
} finally {
    if (page) {
        try {
            if (originalProfile && PROFILE_LABEL[originalProfile]) {
                await selectAutonomy(page, PROFILE_LABEL[originalProfile]);
            }
        } catch {
            // Best-effort preference restoration on a disposable validation database.
        }
        if (fixtureId) {
            try {
                fixtureDeleted = Boolean(await callKw(page, "res.partner", "unlink", [[fixtureId]]));
            } catch {
                fixtureDeleted = false;
            }
        }
    }
    if (context) await context.close();
    await browser.close();
    if (fixtureId && !fixtureDeleted) {
        console.error("P5.5 fixture cleanup was not confirmed; disposable database cleanup remains required");
    }
}
