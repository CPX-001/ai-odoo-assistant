/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";

import {
    assistantPanelService,
    loadAgentPolicy,
} from "./assistant_panel_service";

const ACCOUNT_STATES = new Set([
    "authenticated",
    "authentication_error",
    "codex_unavailable",
    "login_pending",
    "not_authenticated",
]);
const LOGIN_POLL_DELAY_MS = 5000;
const AUTHENTICATED_POLL_DELAY_MS = 60000;

function exactKeys(value, expected) {
    return (
        value !== null &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        Object.keys(value).sort().join("|") === [...expected].sort().join("|")
    );
}

function normalizeNullableString(value, maximum = 512) {
    return value === null || value === undefined
        ? null
        : typeof value === "string" && value.length <= maximum
          ? value
          : undefined;
}

function normalizeRateLimits(rows) {
    if (!Array.isArray(rows) || rows.length > 16) {
        return null;
    }
    const normalized = [];
    for (const row of rows) {
        if (!row || typeof row !== "object" || Array.isArray(row)) {
            return null;
        }
        const item = {};
        for (const [key, value] of Object.entries(row)) {
            if (typeof key !== "string" || key.length > 128) {
                return null;
            }
            if (
                value !== null &&
                typeof value !== "string" &&
                typeof value !== "number" &&
                typeof value !== "boolean"
            ) {
                return null;
            }
            item[key] = value;
        }
        normalized.push(item);
    }
    return normalized;
}

export function normalizeRuntimeAccount(response) {
    if (
        !exactKeys(response, [
            "account",
            "can_configure",
            "login",
            "ok",
            "requires_setup",
            "state",
        ]) ||
        response.ok !== true ||
        !ACCOUNT_STATES.has(response.state) ||
        typeof response.can_configure !== "boolean" ||
        typeof response.requires_setup !== "boolean" ||
        response.requires_setup !== (response.state !== "authenticated")
    ) {
        return null;
    }

    let account = null;
    if (response.account !== null) {
        if (
            !exactKeys(response.account, ["auth_mode", "email", "plan_type", "rate_limits"])
        ) {
            return null;
        }
        const authMode = normalizeNullableString(response.account.auth_mode);
        const email = normalizeNullableString(response.account.email);
        const planType = normalizeNullableString(response.account.plan_type);
        const rateLimits = normalizeRateLimits(response.account.rate_limits);
        if (
            authMode === undefined ||
            email === undefined ||
            planType === undefined ||
            rateLimits === null
        ) {
            return null;
        }
        account = {
            auth_mode: authMode,
            email,
            plan_type: planType,
            rate_limits: rateLimits,
        };
    }

    let login = null;
    if (response.login !== null) {
        if (!exactKeys(response.login, ["user_code", "verification_url"])) {
            return null;
        }
        const verificationUrl = normalizeNullableString(response.login.verification_url, 2048);
        const userCode = normalizeNullableString(response.login.user_code, 128);
        if (verificationUrl === undefined || userCode === undefined) {
            return null;
        }
        login = {
            verification_url: verificationUrl,
            user_code: userCode,
        };
    }

    if (!response.can_configure && (account !== null || login !== null)) {
        return null;
    }
    if (response.state === "authenticated" && response.can_configure && account === null) {
        return null;
    }
    if (response.state === "login_pending" && response.can_configure && login === null) {
        return null;
    }

    return {
        ok: true,
        state: response.state,
        requires_setup: response.requires_setup,
        can_configure: response.can_configure,
        account,
        login,
    };
}

function applyRuntimeAccount(state, payload) {
    state.runtimeState = payload.state;
    state.runtimeCanConfigure = payload.can_configure;
    state.runtimeAccount = payload.account;
    state.runtimeVerificationUrl = payload.login?.verification_url || null;
    state.runtimeUserCode = payload.login?.user_code || null;
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const service = super.start(env, dependencies);
        const state = service.state;
        const baseClose = service.close.bind(service);
        const baseRefreshContext = service.refreshContext.bind(service);
        const baseLoadHistory = service.loadHistory.bind(service);
        const baseNewConversation = service.newConversation.bind(service);
        const baseSelectConversation = service.selectConversation.bind(service);
        const baseSubmit = service.submit.bind(service);
        let accountPoll = null;

        state.runtimeActionLoading = false;
        state.runtimeAccount = null;
        state.runtimeVerificationUrl = null;
        state.runtimeUserCode = null;
        state.chatBootstrapped = false;

        const clearAccountPoll = () => {
            if (accountPoll !== null) {
                globalThis.clearTimeout?.(accountPoll);
                accountPoll = null;
            }
        };

        const pageIsVisible = () => globalThis.document?.visibilityState !== "hidden";

        const lockChat = () => {
            state.chatBootstrapped = false;
            state.historyView = false;
            state.conversations = [];
            state.messages = [];
            state.result = null;
            state.actionReceipt = null;
        };

        const initializeChat = async () => {
            if (
                state.runtimeState !== "authenticated" ||
                state.chatBootstrapped
            ) {
                return false;
            }
            state.chatBootstrapped = true;
            baseRefreshContext();
            await Promise.all([
                baseLoadHistory(),
                loadAgentPolicy({ state, rpcCall: rpc }),
            ]);
            return true;
        };

        const refreshRuntimeAccount = async ({ bootstrap = false } = {}) => {
            if (bootstrap) {
                state.runtimeLoading = true;
                state.runtimeState = null;
                state.runtimeAccount = null;
                state.runtimeVerificationUrl = null;
                state.runtimeUserCode = null;
                lockChat();
            }
            try {
                const payload = normalizeRuntimeAccount(
                    await rpc("/odoo_ai/v1/runtime-account", { action: "status" })
                );
                if (!payload) {
                    state.runtimeState = "authentication_error";
                    state.runtimeCanConfigure = false;
                    state.runtimeAccount = null;
                    lockChat();
                    return false;
                }
                applyRuntimeAccount(state, payload);
                if (payload.state === "authenticated") {
                    await initializeChat();
                } else {
                    lockChat();
                }
                return true;
            } catch {
                state.runtimeState = "authentication_error";
                state.runtimeCanConfigure = false;
                state.runtimeAccount = null;
                lockChat();
                return false;
            } finally {
                if (bootstrap) {
                    state.runtimeLoading = false;
                }
            }
        };

        const scheduleAccountPoll = () => {
            clearAccountPoll();
            if (!state.isOpen || !pageIsVisible()) {
                return;
            }
            const delay =
                state.runtimeState === "login_pending"
                    ? LOGIN_POLL_DELAY_MS
                    : state.runtimeState === "authenticated"
                      ? AUTHENTICATED_POLL_DELAY_MS
                      : null;
            if (delay === null) {
                return;
            }
            accountPoll = globalThis.setTimeout?.(async () => {
                accountPoll = null;
                if (!state.isOpen || !pageIsVisible()) {
                    return;
                }
                await refreshRuntimeAccount();
                scheduleAccountPoll();
            }, delay);
        };

        globalThis.document?.addEventListener?.("visibilitychange", () => {
            if (pageIsVisible()) {
                scheduleAccountPoll();
            } else {
                clearAccountPoll();
            }
        });

        const runtimeAction = async (action) => {
            if (state.runtimeActionLoading) {
                return false;
            }
            state.runtimeActionLoading = true;
            state.errorCode = null;
            try {
                const payload = normalizeRuntimeAccount(
                    await rpc("/odoo_ai/v1/runtime-account", { action })
                );
                if (!payload) {
                    state.runtimeState = "authentication_error";
                    state.runtimeAccount = null;
                    lockChat();
                    return false;
                }
                applyRuntimeAccount(state, payload);
                if (payload.state === "authenticated") {
                    await initializeChat();
                } else {
                    lockChat();
                }
                scheduleAccountPoll();
                return true;
            } catch {
                state.runtimeState = "authentication_error";
                state.runtimeAccount = null;
                lockChat();
                return false;
            } finally {
                state.runtimeActionLoading = false;
                state.runtimeLoading = false;
            }
        };

        const open = () => {
            state.isOpen = true;
            void refreshRuntimeAccount({ bootstrap: true }).then(scheduleAccountPoll);
        };

        service.open = open;
        service.close = () => {
            clearAccountPoll();
            baseClose();
        };
        service.toggle = () => {
            if (state.isOpen) {
                service.close();
            } else {
                open();
            }
        };
        service.refreshContext = () => {
            if (state.runtimeState === "authenticated") {
                baseRefreshContext();
            }
        };
        service.loadHistory = (conversationId = state.conversationId) => {
            if (state.runtimeState !== "authenticated") {
                return Promise.resolve(false);
            }
            return baseLoadHistory(conversationId);
        };
        service.newConversation = () => {
            if (state.runtimeState !== "authenticated") {
                return false;
            }
            return baseNewConversation();
        };
        service.selectConversation = (conversationId) => {
            if (state.runtimeState !== "authenticated") {
                return Promise.resolve(false);
            }
            return baseSelectConversation(conversationId);
        };
        service.submit = async (message) => {
            const sent = await baseSubmit(message);
            if (
                !sent &&
                ["authentication_failed", "codex_not_connected", "codex_unavailable"].includes(
                    state.errorCode
                )
            ) {
                await refreshRuntimeAccount();
                scheduleAccountPoll();
            }
            return sent;
        };
        service.refreshRuntimeAccount = async () => {
            if (state.runtimeActionLoading) {
                return false;
            }
            state.runtimeActionLoading = true;
            try {
                return await refreshRuntimeAccount();
            } finally {
                state.runtimeActionLoading = false;
                scheduleAccountPoll();
            }
        };
        service.connectRuntimeAccount = () => runtimeAction("connect");
        service.cancelRuntimeLogin = () => runtimeAction("cancel");
        service.logoutRuntimeAccount = () => runtimeAction("logout");

        return service;
    },
});
