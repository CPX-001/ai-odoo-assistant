/** Real-browser M4 acceptance harness for the causal sale.order explanation. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

function required(name) {
    const value = process.env[name]?.trim();
    assert.ok(value, `${name} is required`);
    return value;
}

const odooBaseUrl = required("M4_ODOO_BASE_URL").replace(/\/$/, "");
const assistantBaseUrl = required("M4_ASSISTANT_BASE_URL").replace(/\/$/, "");
const database = required("M4_ODOO_DATABASE");
const login = required("M4_E2E_LOGIN");
const password = required("M4_E2E_PASSWORD");
const allowedOrderId = Number(required("M4_ALLOWED_ORDER_ID"));
const allowedOrderName = required("M4_ALLOWED_ORDER_NAME");
const deniedOrderId = Number(required("M4_DENIED_ORDER_ID"));
const expectedMode = process.env.M4_EXPECT_MODE?.trim() || "positive";
const forbiddenValues = (process.env.M4_FORBIDDEN_VALUES || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);

assert.ok(Number.isSafeInteger(allowedOrderId) && allowedOrderId > 0);
assert.ok(Number.isSafeInteger(deniedOrderId) && deniedOrderId > 0);
assert.ok(["positive", "stale", "engine_unavailable"].includes(expectedMode));

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
const browserRequests = [];
const bridgeExchanges = [];
const bridgePath = "/odoo_ai/v1/turn";

page.on("request", (request) => {
    browserRequests.push(request.url());
    if (request.url().includes(bridgePath)) {
        bridgeExchanges.push({ request: request.postData() || "", response: "" });
    }
});
async function loginAndOpen(orderId) {
    await page.goto(`${odooBaseUrl}/web/login?db=${encodeURIComponent(database)}`);
    await page.locator('input[name="login"]').fill(login);
    await page.locator('input[name="password"]').fill(password);
    await Promise.all([
        page.waitForURL((url) => !url.pathname.endsWith("/web/login")),
        page.locator('button[type="submit"]').click(),
    ]);
    await page.goto(`${odooBaseUrl}/web#id=${orderId}&model=sale.order&view_type=form`);
    await page.locator(".o_form_view").waitFor();
    await page.getByRole("button", { name: "Abrir AI Assistant" }).click();
    await page.getByText(`sale.order #${orderId}`, { exact: true }).waitFor();
}

async function submit(question) {
    await page.getByLabel("Pregunta").fill(question);
    await page.getByRole("button", { name: "Enviar", exact: true }).click();
}

try {
    await loginAndOpen(allowedOrderId);
    const bridgeResponsePromise = page.waitForResponse(
        (response) => response.url().includes(bridgePath),
        { timeout: 240_000 }
    );
    await submit("¿Por qué al confirmar este pedido se crea una tarea?");
    const bridgeResponse = await bridgeResponsePromise;
    assert.equal(bridgeExchanges.length, 1, "expected one positive explain exchange");
    bridgeExchanges[0].response = await bridgeResponse.text();
    const request = JSON.parse(bridgeExchanges[0].request);
    assert.deepEqual(Object.keys(request.params).sort(), ["message", "screen", "workflow"]);
    assert.equal(request.params.workflow, "EXPLAIN");
    assert.equal(request.params.screen.model, "sale.order");
    assert.equal(request.params.screen.res_id, allowedOrderId);
    const rpc = JSON.parse(bridgeExchanges[0].response);
    const response = rpc.result;

    if (expectedMode === "engine_unavailable") {
        await page.getByText("El motor de razonamiento no está disponible.", { exact: true }).waitFor();
    } else if (expectedMode === "stale") {
        await page.locator(".o_ai_assistant_result, .alert-danger").first().waitFor();
    } else {
        assert.equal(response.ok, true, JSON.stringify(response));
        const result = page.locator(".o_ai_assistant_result");
        await result.waitFor();
        await result.locator(".o_ai_assistant_answer").waitFor();
        await result.locator("summary", { hasText: `Registro: ${allowedOrderName}` }).waitFor();
        await result.locator("summary", { hasText: "Source: odoo_ai_m3_sale_project" }).waitFor();
    }

    if (expectedMode === "engine_unavailable") {
        assert.deepEqual(response, { error: { code: "engine_unavailable" }, ok: false });
    } else if (expectedMode === "stale") {
        if (response.ok) {
            assert.notEqual(response.confidence, "high");
            assert.ok(!response.citations.some((citation) => citation.kind === "source"));
            assert.ok(response.limitations.length > 0);
        } else {
            assert.ok(
                ["engine_timeout", "engine_unavailable", "evidence_unavailable"].includes(
                    response.error.code
                )
            );
        }
    } else {
        assert.equal(response.ok, true);
        assert.ok(["high", "medium"].includes(response.confidence));
        const answer = response.answer.toLocaleLowerCase("es");
        assert.match(answer, /action_confirm/);
        assert.match(answer, /project\.task|tarea/);
        assert.match(answer, /odoo_ai_m3_sale_project|m[oó]dulo|extensi[oó]n/);
        const record = response.citations.find((citation) => citation.kind === "record");
        const source = response.citations.find((citation) => citation.kind === "source");
        assert.ok(record && source, "record and source citations are required");
        assert.equal(record.model, "sale.order");
        assert.equal(record.id, allowedOrderId);
        assert.equal(record.display_name, allowedOrderName);
        assert.ok(Date.parse(record.captured_at));
        assert.equal(source.module, "odoo_ai_m3_sale_project");
        assert.equal(source.logical_path, "odoo_ai_m3_sale_project/models/sale_order.py");
        assert.ok(source.start_line > 0 && source.end_line >= source.start_line);
        assert.match(source.fingerprint, /^sha256:[0-9a-f]{64}$/);

        const denied = await page.evaluate(async ({ deniedOrderId }) => {
            const result = await fetch("/odoo_ai/v1/explain", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    id: 909,
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                        message: "Explica este pedido",
                        screen: {
                            action_id: null,
                            allowed_context_subset: {
                                active_id: deniedOrderId,
                                active_ids: [deniedOrderId],
                                active_model: "sale.order",
                            },
                            captured_at: new Date().toISOString(),
                            menu_id: null,
                            model: "sale.order",
                            res_id: deniedOrderId,
                            selected_ids: [deniedOrderId],
                            view_type: "form",
                        },
                    },
                }),
            });
            return await result.json();
        }, { deniedOrderId });
        assert.deepEqual(denied.result, { error: { code: "access_denied" }, ok: false });
    }

    const assistantOrigin = new URL(assistantBaseUrl).origin;
    assert.ok(
        browserRequests.every((url) => new URL(url).origin !== assistantOrigin),
        "the browser called the Assistant Service directly"
    );
    const observed = JSON.stringify(bridgeExchanges);
    for (const forbidden of [
        "delegation_token",
        "X-Odoo-AI-Delegation",
        "X-Odoo-AI-Shared-Secret",
        ...forbiddenValues,
    ]) {
        assert.ok(!observed.includes(forbidden), `browser observed forbidden value: ${forbidden}`);
    }
    console.log("M4_E2E_BROWSER=" + JSON.stringify({
        browser_to_assistant_requests: 0,
        mode: expectedMode,
        response,
    }));
} finally {
    await browser.close();
}
