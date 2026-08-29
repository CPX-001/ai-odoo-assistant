/** Real Chromium P5.4 approval-state gate through the current Odoo-native turn path. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const GATE = "P5-REAL-APPROVAL-UX";

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

async function callKw(page, model, method, args) {
    return jsonRpc(page, `/web/dataset/call_kw/${model}/${method}`, {
        model,
        method,
        args,
        kwargs: { context: {} },
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

async function readReference(page, recordId) {
    const rows = await callKw(page, "res.partner", "read", [[recordId], ["ref"]]);
    assert.equal(rows.length, 1);
    return rows[0].ref || "";
}

async function waitForReference(page, recordId, expected) {
    const deadline = Date.now() + 120_000;
    while (Date.now() < deadline) {
        if ((await readReference(page, recordId)) === expected) return;
        await page.waitForTimeout(500);
    }
    assert.fail("approved fixture value was not observed before timeout");
}

const gateId = option("--gate");
assert.equal(gateId, GATE, `--gate must be ${GATE}`);
const decision = option("--decision") || "reject";
assert.ok(["approve", "reject"].includes(decision), "--decision must be approve or reject");
const baseUrl = required("ODOO_AI_P5_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P5_DB");
const loginName = required("ODOO_AI_P5_LOGIN");
const password = required("ODOO_AI_P5_PASSWORD");
const recordId = positiveInteger("ODOO_AI_P5_APPROVAL_RECORD_ID");
const actionId = positiveInteger("ODOO_AI_P5_APPROVAL_ACTION_ID");
assert.ok(database.startsWith("odoo_ai_"), "P5.4 gate requires a disposable odoo_ai_* database");

const browser = await chromium.launch({ headless: true });
try {
    const context = await browser.newContext();
    const page = await context.newPage();
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));

    await login(page, { baseUrl, database, loginName, password });
    await page.goto(
        `${baseUrl}/web#id=${recordId}&action=${actionId}`
        + `&model=res.partner&view_type=form`
    );
    await page.locator(".o_form_view").waitFor({ state: "visible", timeout: 60_000 });
    await page.getByRole("button", { name: "Abrir AI Assistant" }).click();
    await page.getByText(`res.partner #${recordId}`, { exact: true }).waitFor();
    await selectAutonomy(page, "Estricto");

    const before = await readReference(page, recordId);
    const proposed = `P54-APPROVAL-${decision.toUpperCase()}-${Date.now().toString(36)}`;
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
        + "no ejecutes ni afirmes éxito antes de aprobar."
    );
    await page.getByRole("button", { name: "Enviar mensaje" }).click();
    const queuedEnvelope = await (await queuedResponse).json();
    assert.ok(!queuedEnvelope.error, JSON.stringify(queuedEnvelope.error));
    const queued = queuedEnvelope.result;
    assert.equal(queued?.ok, true);
    assert.equal(typeof queued.turn_id, "string");

    const approval = page.locator(".o_ai_assistant_confirmation");
    await approval.waitFor({ state: "visible", timeout: 180_000 });
    assert.equal(
        await approval.evaluate((node) => Boolean(node.closest(".o_ai_assistant_message_assistant"))),
        false,
        "approval was rendered as Assistant prose"
    );

    const status = await jsonRpc(page, "/odoo_ai/v1/turn/status", {
        turn_id: queued.turn_id,
        after_sequence: 0,
    });
    assert.equal(status?.ok, true);
    assert.equal(status.turn_id, queued.turn_id);
    assert.equal(status.state, "awaiting_confirmation");
    const plan = status.response?.plan;
    assert.equal(plan?.plan_id, queued.turn_id);
    assert.equal(plan?.state, "awaiting_confirmation");
    assert.equal(plan?.requires_confirmation, true);
    assert.ok(Array.isArray(plan?.steps) && plan.steps.length > 0);
    const step = plan.steps.find((item) => item.capability === "odoo.record.patch");
    assert.ok(step, "approval plan omitted odoo.record.patch");
    assert.ok(["low", "moderate", "high", "protected"].includes(step.risk));
    assert.ok(["policy", "always"].includes(step.approval));
    const approvalText = await approval.innerText();
    for (const visible of ["Confirmar acción", step.title, step.summary, step.capability, step.risk]) {
        assert.ok(approvalText.includes(visible), `approval omitted visible plan detail: ${visible}`);
    }

    const continueButton = approval.getByRole("button", { name: "Continuar" });
    const cancelButton = approval.getByRole("button", { name: "Cancelar" });
    await continueButton.waitFor({ state: "visible" });
    await cancelButton.waitFor({ state: "visible" });
    assert.equal(await readReference(page, recordId), before, "record changed before approval");

    await selectAutonomy(page, "Equilibrado");
    assert.equal(await approval.count(), 1, "preference change replaced the pending approval");
    const afterPreference = await jsonRpc(page, "/odoo_ai/v1/turn/status", {
        turn_id: queued.turn_id,
        after_sequence: 0,
    });
    assert.equal(afterPreference.state, "awaiting_confirmation");
    assert.equal(afterPreference.response?.plan?.plan_id, queued.turn_id);
    await selectAutonomy(page, "Estricto");

    const decisionResponse = page.waitForResponse(
        (response) =>
            new URL(response.url()).pathname === "/odoo_ai/v1/turn/plan-decision" &&
            response.request().method() === "POST",
        { timeout: 60_000 }
    );
    await (decision === "approve" ? continueButton : cancelButton).click();
    const wireResponse = await decisionResponse;
    const request = JSON.parse(wireResponse.request().postData() || "{}");
    assert.deepEqual(Object.keys(request.params || {}).sort(), ["decision", "plan_id"]);
    assert.equal(request.params.plan_id, queued.turn_id);
    assert.equal(request.params.decision, decision);
    const decisionEnvelope = await wireResponse.json();
    assert.ok(!decisionEnvelope.error, JSON.stringify(decisionEnvelope.error));
    assert.equal(decisionEnvelope.result?.ok, true);
    assert.equal(decisionEnvelope.result?.plan_id, queued.turn_id);
    assert.equal(decisionEnvelope.result?.state, decision === "approve" ? "authorized" : "rejected");

    if (decision === "approve") {
        await waitForReference(page, recordId, proposed);
        assert.equal(await readReference(page, recordId), proposed);
        assert.equal(await callKw(page, "res.partner", "write", [[recordId], { ref: before }]), true);
        assert.equal(await readReference(page, recordId), before);
    } else {
        await approval.waitFor({ state: "hidden", timeout: 30_000 });
        assert.equal(await readReference(page, recordId), before);
    }
    assert.deepEqual(browserErrors, []);

    console.log(JSON.stringify({
        gate: GATE,
        result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        decision,
        dedicated_approval_state: true,
        visible_plan_step_risk: true,
        controls_bound_to_persisted_turn: true,
        preference_change_preserved_turn: true,
        preapproval_business_write: false,
        fixture_restored: true,
    }));

    await context.close();
} finally {
    await browser.close();
}
