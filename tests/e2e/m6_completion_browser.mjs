/** Real Chromium acceptance for M6 safe create and curated sale confirmation. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

function required(name) {
    const value = process.env[name]?.trim();
    assert.ok(value, `${name} is required`);
    return value;
}

const odooBaseUrl = required("M6_ODOO_BASE_URL").replace(/\/$/, "");
const assistantBaseUrl = required("M6_ASSISTANT_BASE_URL").replace(/\/$/, "");
const database = required("M6_ODOO_DATABASE");
const password = required("M6_E2E_PASSWORD");
const loginA = required("M6_E2E_LOGIN_A");
const loginB = required("M6_E2E_LOGIN_B");
const fixture = JSON.parse(required("M6_COMPLETION_FIXTURE"));
const turnPath = "/odoo_ai/v1/turn";
const decisionPath = "/odoo_ai/v1/action-decision";
const browser = await chromium.launch({ headless: true });
const browserRequests = [];
const browserConsole = [];
const exchanges = [];
const sessions = [];

async function userPage(login) {
    const context = await browser.newContext();
    sessions.push(context);
    const page = await context.newPage();
    page.on("console", (message) => browserConsole.push(message.text()));
    page.on("pageerror", (error) => browserConsole.push(error.message));
    page.on("request", (request) => {
        browserRequests.push(request.url());
        if ([turnPath, decisionPath].some((path) => request.url().includes(path))) {
            exchanges.push({
                path: new URL(request.url()).pathname,
                request: request.postData() || "",
                response: "",
            });
        }
    });
    await page.goto(`${odooBaseUrl}/web/login?db=${encodeURIComponent(database)}`);
    await page.locator('input[name="login"]').fill(login);
    await page.locator('input[name="password"]').fill(password);
    await Promise.all([
        page.waitForURL((url) => !url.pathname.endsWith("/web/login")),
        page.locator('button[type="submit"]').click(),
    ]);
    return page;
}

async function jsonRpc(page, path, params) {
    return page.evaluate(
        async ({ path: rpcPath, params: rpcParams }) => {
            const response = await fetch(rpcPath, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    id: Math.floor(Math.random() * 1_000_000),
                    jsonrpc: "2.0",
                    method: "call",
                    params: rpcParams,
                }),
            });
            return response.json();
        },
        { path, params }
    );
}

async function callKw(page, model, method, args, kwargs = {}) {
    const envelope = await jsonRpc(page, `/web/dataset/call_kw/${model}/${method}`, {
        args,
        kwargs: { context: {}, ...kwargs },
        method,
        model,
    });
    assert.ok(!envelope.error, JSON.stringify(envelope.error));
    return envelope.result;
}

async function openRecord(page, target) {
    const menu = target.menuId ? `&menu_id=${target.menuId}` : "";
    await page.goto(
        `${odooBaseUrl}/web#id=${target.recordId}&action=${target.actionId}`
        + `&model=${encodeURIComponent(target.model)}&view_type=form${menu}`
    );
    await page.locator(".o_form_view").waitFor();
    await page.getByRole("button", { name: "Abrir AI Assistant" }).click();
    await page.getByText(`${target.model} #${target.recordId}`, { exact: true }).waitFor();
}

async function submit(page, target, question) {
    await openRecord(page, target);
    const before = exchanges.length;
    await page.getByLabel("Flujo").selectOption("ACTION");
    await page.getByLabel("Pregunta").fill(question);
    const pending = page.waitForResponse(
        (response) => response.url().includes(turnPath),
        { timeout: 220_000 }
    );
    await page.getByRole("button", { name: "Enviar", exact: true }).click();
    const response = await pending;
    assert.equal(exchanges.length, before + 1);
    exchanges.at(-1).response = await response.text();
    const wire = JSON.parse(exchanges.at(-1).request);
    assert.deepEqual(Object.keys(wire.params).sort(), ["message", "screen", "workflow"]);
    assert.equal(wire.params.screen.model, target.model);
    assert.equal(wire.params.screen.res_id, target.recordId);
    const result = JSON.parse(exchanges.at(-1).response).result;
    if (result.ok) {
        await page.locator(".o_ai_assistant_action_preview").waitFor();
    }
    return result;
}

async function decide(page, decision) {
    const before = exchanges.length;
    const pending = page.waitForResponse(
        (response) => response.url().includes(decisionPath),
        { timeout: 220_000 }
    );
    await page.getByRole("button", {
        name: decision === "approve" ? "Aprobar y verificar" : "Cancelar",
        exact: true,
    }).click();
    const response = await pending;
    assert.equal(exchanges.length, before + 1);
    exchanges.at(-1).response = await response.text();
    const wire = JSON.parse(exchanges.at(-1).request);
    assert.deepEqual(Object.keys(wire.params).sort(), ["decision", "proposal_id"]);
    assert.equal(wire.params.decision, decision);
    return JSON.parse(exchanges.at(-1).response).result;
}

async function createdItemCount(page, name) {
    return callKw(page, fixture.create_model, "search_count", [[[
        "name", "=", name,
    ]]]);
}

async function saleState(page, id) {
    const rows = await callKw(
        page,
        "sale.order",
        "read",
        [[id], ["name", "state", "m6_confirm_count"]]
    );
    assert.equal(rows.length, 1);
    return rows[0];
}

function assertCreateProposal(result, name) {
    assert.equal(result.ok, true, JSON.stringify(result));
    assert.equal(result.proposal.action_kind, "record_create");
    assert.deepEqual(result.proposal.target, { model: fixture.create_model });
    const value = result.proposal.values.find((item) => item.field === "name");
    assert.ok(value, JSON.stringify(result.proposal));
    assert.equal(value.value.value, name);
}

function assertBusinessProposal(result, id) {
    assert.equal(result.ok, true, JSON.stringify(result));
    assert.equal(result.proposal.action_kind, "business_action");
    assert.equal(result.proposal.action_id, "sale.order.confirm.v1");
    assert.deepEqual(result.proposal.target, { model: "sale.order", record_id: id });
    assert.equal(result.proposal.state_before, "draft");
    assert.deepEqual(result.proposal.expected_states, ["sale", "done"]);
}

const createTarget = {
    actionId: fixture.create_action_id,
    menuId: fixture.create_menu_id,
    model: fixture.create_model,
    recordId: fixture.create_seed_id,
};
const saleTarget = (recordId) => ({
    actionId: fixture.sale_action_id,
    menuId: fixture.sale_menu_id,
    model: "sale.order",
    recordId,
});

try {
    const page = await userPage(loginA);

    const createHappyName = "M6 Created Happy";
    assert.equal(await createdItemCount(page, createHappyName), 0);
    const createHappy = await submit(
        page,
        createTarget,
        `Create exactly one NEW ${fixture.create_model} with only name equal to ${createHappyName}. Do not modify the current record and do not call odoo.preview_record_patch. Call odoo.get_effective_write_schema then odoo.preview_record_create; do not claim success before approval.`
    );
    assertCreateProposal(createHappy, createHappyName);
    assert.equal(await createdItemCount(page, createHappyName), 0);
    await page.getByText("nuevo registro", { exact: true }).waitFor();
    const createHappyReceipt = await decide(page, "approve");
    assert.equal(createHappyReceipt.state, "verified", JSON.stringify(createHappyReceipt));
    assert.equal(await createdItemCount(page, createHappyName), 1);

    const createRejectName = "M6 Created Reject";
    const createReject = await submit(
        page,
        createTarget,
        `Create exactly one NEW ${fixture.create_model} with only name equal to ${createRejectName}. Do not update the current record. Call odoo.get_effective_write_schema and odoo.preview_record_create only.`
    );
    assertCreateProposal(createReject, createRejectName);
    const createRejected = await decide(page, "reject");
    assert.equal(createRejected.state, "rejected");
    assert.equal(await createdItemCount(page, createRejectName), 0);

    const createAmbiguousName = "M6 Created Ambiguous";
    const createAmbiguous = await submit(
        page,
        createTarget,
        `Create exactly one NEW ${fixture.create_model} with only name equal to ${createAmbiguousName}. Never call the patch tool; call the schema tool and odoo.preview_record_create.`
    );
    assertCreateProposal(createAmbiguous, createAmbiguousName);
    const createAmbiguousReceipt = await decide(page, "approve");
    assert.equal(
        createAmbiguousReceipt.state,
        "verified",
        JSON.stringify(createAmbiguousReceipt)
    );
    assert.equal(await createdItemCount(page, createAmbiguousName), 1);
    const createReplay = await jsonRpc(page, decisionPath, {
        proposal_id: createAmbiguous.proposal.proposal_id,
        decision: "approve",
    });
    assert.deepEqual(createReplay.result, {
        error: { code: "proposal_already_decided" },
        ok: false,
    });
    assert.equal(await createdItemCount(page, createAmbiguousName), 1);

    const businessHappy = await submit(
        page,
        saleTarget(fixture.quotations.happy),
        "Confirm this exact quotation. Call only odoo.preview_business_action with action_id sale.order.confirm.v1 and wait for approval."
    );
    assertBusinessProposal(businessHappy, fixture.quotations.happy);
    assert.equal((await saleState(page, fixture.quotations.happy)).m6_confirm_count, 0);
    await page.getByText("sale.order.confirm.v1", { exact: true }).waitFor();
    const businessHappyReceipt = await decide(page, "approve");
    assert.equal(businessHappyReceipt.state, "verified");
    const happyState = await saleState(page, fixture.quotations.happy);
    assert.ok(["sale", "done"].includes(happyState.state));
    assert.equal(happyState.m6_confirm_count, 1);

    const businessReject = await submit(
        page,
        saleTarget(fixture.quotations.reject),
        "Prepare the sale.order.confirm.v1 preview for this quotation and wait."
    );
    assertBusinessProposal(businessReject, fixture.quotations.reject);
    const businessRejected = await decide(page, "reject");
    assert.equal(businessRejected.state, "rejected");
    const rejectedState = await saleState(page, fixture.quotations.reject);
    assert.equal(rejectedState.state, "draft");
    assert.equal(rejectedState.m6_confirm_count, 0);

    const businessStale = await submit(
        page,
        saleTarget(fixture.quotations.stale),
        "Prepare the exact sale.order.confirm.v1 preview for this quotation."
    );
    assertBusinessProposal(businessStale, fixture.quotations.stale);
    await callKw(page, "sale.order", "action_confirm", [[fixture.quotations.stale]]);
    const businessStaleReceipt = await decide(page, "approve");
    assert.equal(businessStaleReceipt.state, "stale");
    assert.equal((await saleState(page, fixture.quotations.stale)).m6_confirm_count, 1);

    const businessAmbiguous = await submit(
        page,
        saleTarget(fixture.quotations.ambiguous),
        "Confirm this quotation using only the exact sale.order.confirm.v1 preview tool, then wait for approval."
    );
    assertBusinessProposal(businessAmbiguous, fixture.quotations.ambiguous);
    const businessAmbiguousReceipt = await decide(page, "approve");
    assert.equal(businessAmbiguousReceipt.state, "verified");
    const ambiguousState = await saleState(page, fixture.quotations.ambiguous);
    assert.ok(["sale", "done"].includes(ambiguousState.state));
    assert.equal(ambiguousState.m6_confirm_count, 1);
    const businessReplay = await jsonRpc(page, decisionPath, {
        proposal_id: businessAmbiguous.proposal.proposal_id,
        decision: "approve",
    });
    assert.deepEqual(businessReplay.result, {
        error: { code: "proposal_already_decided" },
        ok: false,
    });
    assert.equal((await saleState(page, fixture.quotations.ambiguous)).m6_confirm_count, 1);

    const denied = await userPage(loginB);
    const hidden = await jsonRpc(denied, turnPath, {
        message: "Confirm this quotation with sale.order.confirm.v1",
        screen: {
            action_id: fixture.sale_action_id,
            allowed_context_subset: {
                active_id: fixture.quotations.happy,
                active_ids: [fixture.quotations.happy],
                active_model: "sale.order",
            },
            captured_at: new Date().toISOString(),
            menu_id: fixture.sale_menu_id,
            model: "sale.order",
            res_id: fixture.quotations.happy,
            selected_ids: [fixture.quotations.happy],
            view_type: "form",
        },
        workflow: "ACTION",
    });
    assert.equal(hidden.result.ok, false);
    assert.ok(!JSON.stringify(hidden.result).includes(happyState.name));

    const assistantOrigin = new URL(assistantBaseUrl).origin;
    assert.ok(browserRequests.every((url) => new URL(url).origin !== assistantOrigin));
    const observed = JSON.stringify({ browserConsole, exchanges });
    for (const forbidden of [
        "delegation_token",
        "payload_fingerprint",
        "precondition_fingerprint",
        "X-Odoo-AI-Delegation",
        "X-Odoo-AI-Shared-Secret",
        ...(process.env.M6_FORBIDDEN_VALUES || "").split(",").filter(Boolean),
    ]) {
        assert.ok(!observed.includes(forbidden), `browser observed forbidden value: ${forbidden}`);
    }

    console.log("M6_COMPLETION_BROWSER=" + JSON.stringify({
        business: {
            ambiguous: businessAmbiguous,
            ambiguous_receipt: businessAmbiguousReceipt,
            happy: businessHappy,
            happy_receipt: businessHappyReceipt,
            reject_receipt: businessRejected,
            stale_receipt: businessStaleReceipt,
        },
        create: {
            ambiguous: createAmbiguous,
            ambiguous_receipt: createAmbiguousReceipt,
            happy: createHappy,
            happy_receipt: createHappyReceipt,
            reject_receipt: createRejected,
        },
    }));
} finally {
    for (const context of sessions) {
        await context.close();
    }
    await browser.close();
}
