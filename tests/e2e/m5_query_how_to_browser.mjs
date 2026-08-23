/** Real Chromium acceptance for M5 QUERY and HOW_TO through the Odoo bridge. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

function required(name) {
    const value = process.env[name]?.trim();
    assert.ok(value, `${name} is required`);
    return value;
}

const odooBaseUrl = required("M5_ODOO_BASE_URL").replace(/\/$/, "");
const assistantBaseUrl = required("M5_ASSISTANT_BASE_URL").replace(/\/$/, "");
const database = required("M5_ODOO_DATABASE");
const password = required("M5_E2E_PASSWORD");
const loginA = required("M5_E2E_LOGIN_A");
const loginB = required("M5_E2E_LOGIN_B");
const actionId = Number(required("M5_ACTION_ID"));
const menuId = Number(required("M5_MENU_ID"));
const model = required("M5_MODEL");
const hiddenName = required("M5_HIDDEN_NAME");
const mode = process.env.M5_EXPECT_MODE?.trim() || "positive";
const bridgePath = "/odoo_ai/v1/turn";
assert.ok(["positive", "stale", "engine_unavailable"].includes(mode));

const browser = await chromium.launch({ headless: true });
const browserRequests = [];
const exchanges = [];

async function userPage(login) {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on("request", (request) => {
        browserRequests.push(request.url());
        if (request.url().includes(bridgePath)) {
            exchanges.push({ request: request.postData() || "", response: "" });
        }
    });
    await page.goto(`${odooBaseUrl}/web/login?db=${encodeURIComponent(database)}`);
    await page.locator('input[name="login"]').fill(login);
    await page.locator('input[name="password"]').fill(password);
    await Promise.all([
        page.waitForURL((url) => !url.pathname.endsWith("/web/login")),
        page.locator('button[type="submit"]').click(),
    ]);
    await page.goto(
        `${odooBaseUrl}/web#action=${actionId}&model=${encodeURIComponent(model)}`
        + `&view_type=list&menu_id=${menuId}`
    );
    await page.locator(".o_list_view").waitFor();
    await page.getByRole("button", { name: "Abrir AI Assistant" }).click();
    await page.getByText(model, { exact: true }).waitFor();
    return { context, page };
}

async function submit(page, workflow, question) {
    const before = exchanges.length;
    await page.getByLabel("Flujo").selectOption(workflow);
    await page.getByLabel("Pregunta").fill(question);
    const responsePromise = page.waitForResponse(
        (response) => response.url().includes(bridgePath),
        { timeout: 220_000 }
    );
    await page.getByRole("button", { name: "Enviar", exact: true }).click();
    const response = await responsePromise;
    assert.equal(exchanges.length, before + 1);
    exchanges.at(-1).response = await response.text();
    const request = JSON.parse(exchanges.at(-1).request);
    assert.deepEqual(Object.keys(request.params).sort(), ["message", "screen", "workflow"]);
    assert.equal(request.params.workflow, workflow);
    assert.equal(request.params.screen.model, model);
    return JSON.parse(exchanges.at(-1).response).result;
}

const sessions = [];
try {
    const a = await userPage(loginA);
    sessions.push(a.context);
    const queryA = await submit(
        a.page,
        "QUERY",
        "Usa las herramientas de consulta de solo lectura: ¿cuántos registros con estado Open puedo ver en el modelo actual? Responde con el número exacto."
    );
    if (mode === "engine_unavailable") {
        assert.deepEqual(queryA, { error: { code: "engine_unavailable" }, ok: false });
        await a.page.getByText("El motor de razonamiento no está disponible.", { exact: true }).waitFor();
        console.log("M5_E2E_BROWSER=" + JSON.stringify({ mode, query_a: queryA }));
        process.exitCode = 0;
    } else {
        assert.equal(queryA.ok, true, JSON.stringify(queryA));
        assert.equal(queryA.workflow, "QUERY");
        assert.match(queryA.answer, /(?:^|\D)2(?:\D|$)/);
        assert.ok(queryA.citations.some((citation) => citation.kind === "query"));
        assert.ok(!JSON.stringify(queryA).includes(hiddenName));
        await a.page.locator("summary", { hasText: `Consulta: ${model}` }).waitFor();

        const rejected = await submit(
            a.page,
            "QUERY",
            "Elimina todos los elementos guiados abiertos y confirma que se borraron."
        );
        assert.deepEqual(rejected, { error: { code: "query_rejected" }, ok: false });

        const howTo = await submit(
            a.page,
            "HOW_TO",
            "Consulta la documentación configurada: ¿cómo reviso los elementos guiados y localizo su código de guía en esta instalación?"
        );
        if (mode === "stale") {
            if (howTo.ok) {
                assert.notEqual(howTo.confidence, "high");
                assert.ok(!howTo.citations.some((citation) => citation.kind === "document"));
                assert.ok(howTo.limitations.length > 0);
            } else {
                assert.ok(["engine_timeout", "engine_unavailable", "evidence_unavailable"].includes(howTo.error.code));
            }
            console.log("M5_E2E_BROWSER=" + JSON.stringify({
                how_to: howTo,
                mode,
                query_a: queryA,
                rejected,
            }));
        } else {
            assert.equal(howTo.ok, true, JSON.stringify(howTo));
            assert.equal(howTo.workflow, "HOW_TO");
            const kinds = new Set(howTo.citations.map((citation) => citation.kind));
            assert.ok(kinds.has("navigation"));
            assert.ok(kinds.has("schema"));
            assert.ok(kinds.has("document"));
            assert.match(howTo.answer.toLocaleLowerCase("es"), /guided items|elementos guiados/);
            assert.match(howTo.answer, /guide_code|código de guía/i);
            await a.page.locator("summary", { hasText: "Menú:" }).waitFor();
            await a.page.locator("summary", { hasText: `Schema: ${model}` }).waitFor();
            await a.page.locator("summary", { hasText: "Documento:" }).waitFor();

            const b = await userPage(loginB);
            sessions.push(b.context);
            const queryB = await submit(
                b.page,
                "QUERY",
                "Usa las herramientas de consulta de solo lectura: ¿cuántos registros con estado Open puedo ver en el modelo actual? Responde con el número exacto."
            );
            assert.equal(queryB.ok, true, JSON.stringify(queryB));
            assert.match(queryB.answer, /(?:^|\D)1(?:\D|$)/);
            assert.ok(!JSON.stringify(queryB).includes("Visible Alpha"));

            const assistantOrigin = new URL(assistantBaseUrl).origin;
            assert.ok(
                browserRequests.every((url) => new URL(url).origin !== assistantOrigin),
                "Chromium called Assistant Service directly"
            );
            const observed = JSON.stringify(exchanges);
            for (const forbidden of [
                "delegation_token",
                "X-Odoo-AI-Delegation",
                "X-Odoo-AI-Shared-Secret",
                ...(process.env.M5_FORBIDDEN_VALUES || "").split(",").filter(Boolean),
            ]) {
                assert.ok(!observed.includes(forbidden), `browser observed forbidden value: ${forbidden}`);
            }
            console.log("M5_E2E_BROWSER=" + JSON.stringify({
                browser_to_assistant_requests: 0,
                how_to: howTo,
                mode,
                query_a: queryA,
                query_b: queryB,
                rejected,
            }));
        }
    }
} finally {
    for (const context of sessions) {
        await context.close();
    }
    await browser.close();
}
