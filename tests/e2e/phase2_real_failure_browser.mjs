/** Real Chromium Phase 2 failure gates through the Odoo-native queue and status path. */

import assert from "node:assert/strict";
import { chromium } from "playwright";

const GATES = {
    "P2-REAL-AUTH": {
        marker: "__P2_REAL_AUTH__",
        profile: "default",
        state: "failed",
        code: "codex_turn_failed",
        category: "authentication",
        retryability: "after_change",
        effectState: "none",
        userAction: "reconnect",
        includes: ["autenticación", "no se ha iniciado ningún cambio"],
        retryButton: false,
    },
    "P2-REAL-ACL": {
        marker: "__P2_REAL_ACL__",
        profile: "limited",
        state: "failed",
        code: "access_denied",
        category: "odoo_access",
        retryability: "after_change",
        effectState: "none",
        userAction: "request_access",
        includes: ["denegado el acceso", "permisos efectivos"],
        retryButton: false,
    },
    "P2-REAL-TIMEOUT": {
        marker: "__P2_REAL_TIMEOUT__",
        profile: "default",
        state: "failed",
        code: "engine_timeout",
        category: "provider_connection",
        retryability: "safe",
        effectState: "none",
        userAction: "retry",
        includes: ["comunicación", "puedes reintentar esta petición de forma segura"],
        retryButton: true,
    },
    "P2-REAL-TOOLFAIL": {
        marker: "__P2_REAL_TOOLFAIL__",
        profile: "default",
        state: "failed",
        code: "capability_execution_failed",
        category: "capability_execution",
        retryability: "unknown",
        effectState: "none",
        userAction: "review",
        includes: ["herramienta", "comprueba los datos afectados"],
        retryButton: false,
    },
    "P2-REAL-RECOVERY": {
        marker: "__P2_REAL_RECOVERY__",
        profile: "default",
        state: "recovery_required",
        code: "worker_lost_after_write_barrier",
        category: "queue_worker",
        retryability: "never",
        effectState: "unknown",
        userAction: "review",
        includes: ["no se puede confirmar", "no repitas la acción a ciegas"],
        retryButton: false,
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

const gateId = option("--gate");
assert.ok(gateId && GATES[gateId], `--gate must be one of ${Object.keys(GATES).join(", ")}`);
const gate = GATES[gateId];
const baseUrl = required("ODOO_AI_P2_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_P2_DB");
assert.ok(database.startsWith("odoo_ai_"), "Phase 2 fault gates require a disposable odoo_ai_* DB");
const login = required(gate.profile === "limited" ? "ODOO_AI_P2_LIMITED_LOGIN" : "ODOO_AI_P2_LOGIN");
const password = required(
    gate.profile === "limited" ? "ODOO_AI_P2_LIMITED_PASSWORD" : "ODOO_AI_P2_PASSWORD"
);

async function jsonRpc(page, path, params) {
    const envelope = await page.evaluate(
        async ({ path: rpcPath, params: rpcParams }) => {
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
        { path, params }
    );
    assert.ok(!envelope.error, JSON.stringify(envelope.error));
    return envelope.result;
}

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
    await composer.fill(gate.marker);
    await page.getByRole("button", { name: "Enviar mensaje" }).click();
    const queuedEnvelope = await (await queuedResponse).json();
    assert.ok(!queuedEnvelope.error, JSON.stringify(queuedEnvelope.error));
    const queued = queuedEnvelope.result;
    assert.equal(queued?.ok, true);
    assert.equal(typeof queued.turn_id, "string");

    const failureMessage = page.locator(".o_ai_assistant_failure_message").last();
    await failureMessage.waitFor({ state: "visible", timeout: 120_000 });
    const errorBlock = failureMessage.locator("xpath=..");
    const browserText = (await errorBlock.innerText()).toLowerCase();

    const status = await jsonRpc(page, "/odoo_ai/v1/turn/status", {
        turn_id: queued.turn_id,
        after_sequence: 0,
    });
    assert.equal(status.ok, true);
    assert.equal(status.turn_id, queued.turn_id);
    assert.equal(status.state, gate.state);
    assert.equal(status.error_code, gate.code);
    assert.equal(status.failure?.code, gate.code);
    assert.equal(status.failure?.category, gate.category);
    assert.equal(status.failure?.retryability, gate.retryability);
    assert.equal(status.failure?.effect_state, gate.effectState);
    assert.equal(status.failure?.user_action, gate.userAction);
    assert.equal(typeof status.failure?.diagnostic_id, "string");

    for (const fragment of gate.includes) {
        assert.ok(browserText.includes(fragment), `missing browser fragment: ${fragment}\n${browserText}`);
    }
    assert.ok(browserText.includes("código:"), browserText);
    assert.ok(browserText.includes("diagnóstico:"), browserText);

    const retryButton = page.getByRole("button", { name: "Reintentar petición" });
    if (gate.retryButton) {
        await retryButton.waitFor({ state: "visible", timeout: 10_000 });
    } else {
        assert.equal(await retryButton.count(), 0, "blind retry control must not be present");
    }

    const forbidden = [
        status.failure?.safe_summary,
        status.failure?.provider_code,
        status.failure?.safe_details?.fixture_detail,
        "password",
        "stderr",
        "stdout",
        "prompt",
        "authorization",
    ].filter((value) => typeof value === "string" && value.length > 0);
    for (const value of forbidden) {
        assert.ok(!browserText.includes(value.toLowerCase()), `browser leaked forbidden failure detail: ${value}`);
    }
    assert.deepEqual(browserErrors, []);

    console.log(
        JSON.stringify({
            gate: gateId,
            turn_state: status.state,
            code: status.failure.code,
            category: status.failure.category,
            retryability: status.failure.retryability,
            effect_state: status.failure.effect_state,
            user_action: status.failure.user_action,
            browser_retry: gate.retryButton,
            result: "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        })
    );
    await context.close();
} finally {
    await browser.close();
}
