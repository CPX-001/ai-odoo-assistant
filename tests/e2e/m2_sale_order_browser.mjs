/**
 * Real-browser M2 acceptance harness.
 *
 * It exercises Odoo's shipped web assets and JSON-RPC bridge. The process
 * running this script may know the Assistant URL and forbidden test values so
 * it can prove that the browser never sends to that origin or observes them.
 */

import assert from "node:assert/strict";
import { chromium } from "playwright";

function required(name) {
    const value = process.env[name]?.trim();
    assert.ok(value, `${name} is required`);
    return value;
}

const odooBaseUrl = required("M2_ODOO_BASE_URL").replace(/\/$/, "");
const assistantBaseUrl = required("M2_ASSISTANT_BASE_URL").replace(/\/$/, "");
const database = required("M2_ODOO_DATABASE");
const login = required("M2_E2E_LOGIN");
const password = required("M2_E2E_PASSWORD");
const allowedOrderId = Number(required("M2_ALLOWED_ORDER_ID"));
const allowedOrderName = required("M2_ALLOWED_ORDER_NAME");
const deniedOrderId = Number(required("M2_DENIED_ORDER_ID"));
const deniedOrderName = required("M2_DENIED_ORDER_NAME");
const forbiddenValues = (process.env.M2_FORBIDDEN_VALUES || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);

assert.ok(Number.isSafeInteger(allowedOrderId) && allowedOrderId > 0);
assert.ok(Number.isSafeInteger(deniedOrderId) && deniedOrderId > 0);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
const browserRequests = [];
const bridgeExchanges = [];
const bridgeResponseReads = [];
const browserBridgePath = "/odoo_ai/v1/context-read";

page.on("request", (request) => {
    browserRequests.push(request.url());
    if (request.url().includes(browserBridgePath)) {
        bridgeExchanges.push({ request: request.postData() || "", response: "" });
    }
});
page.on("response", (response) => {
    if (!response.url().includes(browserBridgePath)) {
        return;
    }
    const exchange = bridgeExchanges.find((candidate) => !candidate.response);
    if (exchange) {
        bridgeResponseReads.push(
            response.text().then((body) => {
                exchange.response = body;
            })
        );
    }
});

try {
    await page.goto(`${odooBaseUrl}/web/login?db=${encodeURIComponent(database)}`);
    await page.locator('input[name="login"]').fill(login);
    await page.locator('input[name="password"]').fill(password);
    await Promise.all([
        page.waitForURL((url) => !url.pathname.endsWith("/web/login")),
        page.locator('button[type="submit"]').click(),
    ]);

    await page.goto(
        `${odooBaseUrl}/web#id=${allowedOrderId}&model=sale.order&view_type=form`
    );
    await page.locator(".o_form_view").waitFor();
    await page.getByRole("button", { name: "Abrir AI Assistant" }).click();
    await page.getByText(`sale.order #${allowedOrderId}`, { exact: true }).waitFor();
    await page.getByLabel("Pregunta").fill("¿Qué pedido estoy viendo?");
    await page.getByRole("button", { name: "Enviar", exact: true }).click();

    const assistantResult = page.locator(".o_ai_assistant_result");
    await assistantResult
        .getByText(allowedOrderName, { exact: true })
        .first()
        .waitFor();
    await assistantResult
        .getByText("El registro actual se ha releído", { exact: false })
        .waitFor();

    assert.ok(bridgeExchanges.length >= 1, "the panel did not call the Odoo bridge");
    const positive = JSON.parse(bridgeExchanges[0].request);
    assert.deepEqual(Object.keys(positive.params).sort(), ["message", "screen"]);
    const { message, screen } = positive.params;
    assert.equal(message, "¿Qué pedido estoy viendo?");
    assert.equal(screen.model, "sale.order");
    assert.equal(screen.res_id, allowedOrderId);
    for (const untrustedIdentityKey of [
        "uid",
        "company_id",
        "allowed_company_ids",
        "groups",
        "display_name",
    ]) {
        assert.ok(!(untrustedIdentityKey in screen), `${untrustedIdentityKey} leaked into ScreenContext`);
    }

    const negative = await page.evaluate(async ({ deniedOrderId }) => {
        const response = await fetch(
            "/odoo_ai/v1/context-read",
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    id: 808,
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                        message: "¿Qué pedido estoy viendo?",
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
            }
        );
        return { body: await response.json(), status: response.status };
    }, { deniedOrderId });

    assert.equal(negative.status, 200);
    assert.deepEqual(negative.body.result, {
        error: { code: "access_denied" },
        ok: false,
    });
    assert.ok(!JSON.stringify(negative).includes(deniedOrderName));

    await Promise.all(bridgeResponseReads);
    assert.ok(
        bridgeExchanges.every((exchange) => exchange.request && exchange.response),
        "a browser bridge exchange was not fully captured"
    );

    const assistantOrigin = new URL(assistantBaseUrl).origin;
    assert.ok(
        browserRequests.every((url) => new URL(url).origin !== assistantOrigin),
        "the browser called the Assistant Service directly"
    );
    const observedBridgeTraffic = JSON.stringify(bridgeExchanges);
    for (const forbidden of [
        "delegation_token",
        "X-Odoo-AI-Delegation",
        "X-Odoo-AI-Shared-Secret",
        ...forbiddenValues,
    ]) {
        assert.ok(!observedBridgeTraffic.includes(forbidden), `browser observed forbidden value: ${forbidden}`);
    }

    const screenshot = process.env.M2_E2E_SCREENSHOT?.trim();
    if (screenshot) {
        await page.screenshot({ path: screenshot, fullPage: true });
    }
    console.log(
        JSON.stringify({
            allowed_order_id: allowedOrderId,
            browser_origins: [...new Set(browserRequests.map((url) => new URL(url).origin))],
            browser_to_assistant_requests: 0,
            denied_order_id: deniedOrderId,
            negative_error: negative.body.result.error.code,
            positive_display_name: allowedOrderName,
            positive_status: "ok",
        })
    );
} finally {
    await browser.close();
}
