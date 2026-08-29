import assert from "node:assert/strict";

import { chromium } from "playwright";

function required(name) {
    const value = process.env[name]?.trim();
    assert.ok(value, `${name} is required`);
    return value;
}

const base = required("ODOO_AI_HOOT_BASE_URL").replace(/\/$/, "");
const database = required("ODOO_AI_HOOT_DB");
const filter = required("ODOO_AI_HOOT_FILTER");
const canonicalFilter = process.env.ODOO_AI_HOOT_CANONICAL?.trim() || "";
const login = required("ODOO_AI_HOOT_LOGIN");
const password = required("ODOO_AI_HOOT_PASSWORD");
const timeout = Number(process.env.ODOO_AI_HOOT_TIMEOUT_MS || 180_000);
assert.ok(Number.isInteger(timeout) && timeout >= 1_000 && timeout <= 300_000);
function hootHash(value) {
    let hash = 0;
    for (let index = 0; index < value.length; index += 1) {
        hash = (hash << 5) - hash + value.charCodeAt(index);
        hash |= 0;
    }
    return (hash + 16 ** 8).toString(16).slice(-8);
}

const selection = canonicalFilter
    ? `&id=${hootHash(canonicalFilter)}`
    : `&filter=${encodeURIComponent(filter)}`;
const url =
    process.env.ODOO_AI_HOOT_URL?.trim() ||
    `${base}/web/tests?db=${encodeURIComponent(database)}&mod=odoo_ai_assistant&headless&loglevel=2&preset=desktop&timeout=15000${selection}`;

const browser = await chromium.launch({ headless: true });
try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    const errors = [];
    const consoleMessages = [];
    let complete;
    let fail;
    const completion = new Promise((resolve, reject) => {
        complete = resolve;
        fail = reject;
    });
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
        const value = message.text();
        consoleMessages.push(value);
        if (value.includes("Test suite succeeded")) {
            complete();
        } else if (/Some tests failed|Failed [1-9]\d* tests/.test(value)) {
            fail(new Error(value));
        }
    });

    await page.goto(`${base}/web/login?db=${encodeURIComponent(database)}`, {
        waitUntil: "domcontentloaded",
        timeout: 120_000,
    });
    await page.locator('input[name="login"]').fill(login);
    await page.locator('input[name="password"]').fill(password);
    await Promise.all([
        page.waitForURL((current) => !current.pathname.endsWith("/web/login"), {
            timeout: 60_000,
        }),
        page.locator('button[type="submit"]').click(),
    ]);

    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 120_000 });
    let timeoutId;
    try {
        await Promise.race([
            completion,
            new Promise((_, reject) =>
                (timeoutId = setTimeout(
                    () => reject(new Error(`HOOT timed out after ${timeout}ms`)),
                    timeout
                ))
            ),
        ]);
    } catch (error) {
        const diagnostics = consoleMessages
            .filter((value) => /fail|assert|expect|error/i.test(value))
            .slice(-50);
        throw new Error(
            `${error.message}; page_errors=${JSON.stringify(errors)}; diagnostics=${JSON.stringify(diagnostics)}`
        );
    } finally {
        clearTimeout(timeoutId);
    }
    const summary = consoleMessages.find((value) => /Passed \d+ tests/.test(value));
    assert.ok(summary, `HOOT emitted no pass total: ${JSON.stringify(consoleMessages.slice(-20))}`);
    const passed = Number(summary.match(/Passed (\d+) tests/)?.[1]);
    assert.ok(passed > 0, `HOOT filter matched no tests: ${filter}`);
    assert.deepEqual(errors, []);
    console.log(
        `HOOT filtered gate completed: ${canonicalFilter || filter}; ${summary}`
    );
} finally {
    await browser.close();
}
