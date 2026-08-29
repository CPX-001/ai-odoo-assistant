/** @odoo-module **/

import { expect, test } from "@odoo/hoot";

import { normalizeRuntimeAccount } from "@odoo_ai_assistant/services/zz_assistant_auth_service";

test("runtime account accepts an authenticated admin profile", () => {
    const payload = {
        ok: true,
        state: "authenticated",
        requires_setup: false,
        can_configure: true,
        account: {
            auth_mode: "chatgpt",
            email: "admin@example.com",
            plan_type: "plus",
            rate_limits: [
                {
                    limit_id: "codex",
                    limit_name: "Codex",
                    used_percent: 23,
                    window_duration_mins: 300,
                },
            ],
        },
    };

    expect(normalizeRuntimeAccount(payload)).toEqual(payload);
});

test("runtime account accepts externally pending host authentication without login data", () => {
    const payload = {
        ok: true,
        state: "login_pending",
        requires_setup: true,
        can_configure: true,
        account: null,
    };

    expect(normalizeRuntimeAccount(payload)).toEqual(payload);
});

test("runtime account rejects account details for non administrators", () => {
    expect(
        normalizeRuntimeAccount({
            ok: true,
            state: "authenticated",
            requires_setup: false,
            can_configure: false,
            account: {
                auth_mode: "chatgpt",
                email: "secret@example.com",
                plan_type: "plus",
                rate_limits: [],
            },
        })
    ).toBe(null);
});
