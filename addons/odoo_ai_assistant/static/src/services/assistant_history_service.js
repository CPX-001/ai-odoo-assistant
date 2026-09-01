/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import {
    assistantPanelService,
    normalizeActionDecisionResponse,
} from "@odoo_ai_assistant/services/assistant_panel_service";

export const ACTIVE_CHAT_TTL_MS = 30 * 60 * 1000;
export const RECOVERY_PLAN_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const ACTIVE_CHAT_CACHE_VERSION = 1;
const RECOVERY_CACHE_VERSION = 1;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const RECOVERY_ACTIVE_STATES = new Set(["authorized", "executing"]);
const RECOVERY_TERMINAL_STATES = new Set([
    "completed",
    "partial",
    "failed",
    "rejected",
    "expired",
]);

function browserSessionStorage() {
    try {
        return globalThis.sessionStorage || null;
    } catch {
        return null;
    }
}

function browserLocalStorage() {
    try {
        return globalThis.localStorage || null;
    } catch {
        return null;
    }
}

function userScopedKey(name) {
    const host = globalThis.location?.host || "odoo";
    const uid =
        globalThis.odoo?.session_info?.uid ??
        globalThis.odoo?.__session_info__?.uid;
    const userScope = Number.isSafeInteger(uid) && uid > 0 ? String(uid) : "session";
    return `odoo_ai_assistant:${name}:${host}:${userScope}`;
}

export function activeChatStorageKey() {
    return userScopedKey("active_chat");
}

export function recoveryPlanStorageKey() {
    return userScopedKey("recovery_plan");
}

export function loadRecentActiveChat(storage, now = Date.now()) {
    try {
        const raw = storage?.getItem(activeChatStorageKey());
        if (!raw) {
            return null;
        }
        const value = JSON.parse(raw);
        const valid =
            value?.version === ACTIVE_CHAT_CACHE_VERSION &&
            typeof value.conversationId === "string" &&
            UUID_PATTERN.test(value.conversationId) &&
            Number.isFinite(value.touchedAt) &&
            value.touchedAt <= now &&
            now - value.touchedAt <= ACTIVE_CHAT_TTL_MS;
        if (!valid) {
            storage?.removeItem(activeChatStorageKey());
            return null;
        }
        return value.conversationId;
    } catch {
        return null;
    }
}

export function saveRecentActiveChat(storage, conversationId, now = Date.now()) {
    if (typeof conversationId !== "string" || !UUID_PATTERN.test(conversationId)) {
        return false;
    }
    try {
        storage?.setItem(
            activeChatStorageKey(),
            JSON.stringify({
                version: ACTIVE_CHAT_CACHE_VERSION,
                conversationId,
                touchedAt: now,
            })
        );
        return true;
    } catch {
        return false;
    }
}

export function clearRecentActiveChat(storage) {
    try {
        storage?.removeItem(activeChatStorageKey());
        return true;
    } catch {
        return false;
    }
}

export function loadRecoveryPlanId(storage, now = Date.now()) {
    try {
        const raw = storage?.getItem(recoveryPlanStorageKey());
        if (!raw) {
            return null;
        }
        const value = JSON.parse(raw);
        const valid =
            value?.version === RECOVERY_CACHE_VERSION &&
            typeof value.planId === "string" &&
            UUID_PATTERN.test(value.planId) &&
            Number.isFinite(value.touchedAt) &&
            value.touchedAt <= now &&
            now - value.touchedAt <= RECOVERY_PLAN_TTL_MS;
        if (!valid) {
            storage?.removeItem(recoveryPlanStorageKey());
            return null;
        }
        return value.planId;
    } catch {
        return null;
    }
}

export function saveRecoveryPlanId(storage, planId, now = Date.now()) {
    if (typeof planId !== "string" || !UUID_PATTERN.test(planId)) {
        return false;
    }
    try {
        storage?.setItem(
            recoveryPlanStorageKey(),
            JSON.stringify({
                version: RECOVERY_CACHE_VERSION,
                planId,
                touchedAt: now,
            })
        );
        return true;
    } catch {
        return false;
    }
}

export function clearRecoveryPlanId(storage) {
    try {
        storage?.removeItem(recoveryPlanStorageKey());
        return true;
    } catch {
        return false;
    }
}

export function normalizeRecoveryStatusResponse(response, planId) {
    const state = response?.state;
    const plan = response?.plan;
    if (
        response?.ok === true &&
        response.plan_id === planId &&
        (RECOVERY_ACTIVE_STATES.has(state) || RECOVERY_TERMINAL_STATES.has(state)) &&
        plan !== null &&
        typeof plan === "object" &&
        plan.plan_id === planId &&
        plan.state === state
    ) {
        return { receipt: response, plan, errorCode: null };
    }
    const fallback = normalizeActionDecisionResponse(response, planId);
    if (fallback.receipt) {
        return fallback;
    }
    return fallback;
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        const sessionStorage = browserSessionStorage();
        const localStorage = browserLocalStorage();

        // An idle chat cached by the previous page/session is not navigation authority. New panel
        // sessions land on history; an in-memory chat remains visible when the same panel is merely
        // closed and reopened. Recovery has its own durable path below.
        panel.state.conversationId = null;
        panel.state.historyView = true;
        panel.state.recoveryPlanId = loadRecoveryPlanId(localStorage);

        const recoveryPending = () =>
            RECOVERY_ACTIVE_STATES.has(panel.state.result?.plan?.state) ||
            typeof panel.state.recoveryPlanId === "string";
        const isBusy = () =>
            panel.state.loading ||
            panel.state.historyLoading ||
            panel.state.decisionLoading ||
            recoveryPending();

        const clearRecovery = () => {
            panel.state.recoveryPlanId = null;
            clearRecoveryPlanId(localStorage);
        };

        const syncRecoveryFromPlan = (plan) => {
            if (
                RECOVERY_ACTIVE_STATES.has(plan?.state) &&
                UUID_PATTERN.test(plan?.plan_id || "")
            ) {
                panel.state.recoveryPlanId = plan.plan_id;
                saveRecoveryPlanId(localStorage, plan.plan_id);
                return;
            }
            if (plan) {
                clearRecovery();
            }
        };

        const restoreRecovery = async () => {
            const planId = panel.state.recoveryPlanId || loadRecoveryPlanId(localStorage);
            if (!planId) {
                return false;
            }
            panel.state.recoveryPlanId = planId;
            try {
                const response = await rpc("/odoo_ai/v1/agent-plan-status", {
                    plan_id: planId,
                });
                const normalized = normalizeRecoveryStatusResponse(response, planId);
                if (!normalized.receipt) {
                    if (["invalid_context", "access_denied"].includes(normalized.errorCode)) {
                        clearRecovery();
                        return false;
                    }
                    panel.state.errorCode = normalized.errorCode;
                    return true;
                }
                if (RECOVERY_TERMINAL_STATES.has(normalized.plan?.state)) {
                    clearRecovery();
                    if (panel.state.result && normalized.plan) {
                        panel.state.result = { ...panel.state.result, plan: normalized.plan };
                        panel.state.actionReceipt = normalized.receipt;
                    }
                    panel.state.errorCode = null;
                    return false;
                }
                if (!RECOVERY_ACTIVE_STATES.has(normalized.plan?.state)) {
                    panel.state.errorCode = "invalid_response";
                    return true;
                }
                panel.state.result = {
                    ...(panel.state.result || {}),
                    plan: normalized.plan,
                };
                panel.state.actionReceipt = normalized.receipt;
                panel.state.errorCode = null;
                saveRecoveryPlanId(localStorage, planId);
                return true;
            } catch {
                panel.state.errorCode = "service_unavailable";
                return true;
            }
        };

        const showHistory = async () => {
            if (isBusy()) {
                return false;
            }
            clearRecentActiveChat(sessionStorage);
            panel.newConversation();
            panel.state.historyView = true;
            return panel.loadHistory(null);
        };

        const openNormalView = () => {
            // Reopening the same live panel keeps the chat the user was already using. A fresh
            // Assistant entry starts from the history list instead of silently selecting the last
            // idle conversation cached in sessionStorage.
            if (!panel.state.historyView && panel.state.conversationId) {
                return;
            }
            clearRecentActiveChat(sessionStorage);
            panel.newConversation();
            panel.state.historyView = true;
            void panel.loadHistory(null);
        };

        const open = () => {
            panel.state.isOpen = true;
            panel.refreshContext();
            if (recoveryPending()) {
                panel.state.historyView = false;
                void restoreRecovery().then((restored) => {
                    if (!restored) {
                        openNormalView();
                    }
                });
                return;
            }
            openNormalView();
        };

        return {
            ...panel,
            open,
            restoreRecovery,
            close() {
                if (!panel.state.historyView && panel.state.conversationId) {
                    saveRecentActiveChat(sessionStorage, panel.state.conversationId);
                }
                panel.close();
            },
            toggle() {
                if (panel.state.isOpen) {
                    if (!panel.state.historyView && panel.state.conversationId) {
                        saveRecentActiveChat(sessionStorage, panel.state.conversationId);
                    }
                    panel.close();
                } else {
                    open();
                }
            },
            showHistory() {
                void showHistory();
            },
            newConversation() {
                if (isBusy()) {
                    return false;
                }
                clearRecentActiveChat(sessionStorage);
                const created = panel.newConversation();
                panel.state.historyView = false;
                return created !== false;
            },
            async selectConversation(conversationId) {
                if (isBusy()) {
                    return false;
                }
                const loaded = await panel.selectConversation(conversationId);
                if (loaded) {
                    panel.state.historyView = false;
                    saveRecentActiveChat(sessionStorage, panel.state.conversationId);
                }
                return loaded;
            },
            async submit(message) {
                if (isBusy()) {
                    return false;
                }
                const sent = await panel.submit(message);
                if (sent) {
                    syncRecoveryFromPlan(panel.state.result?.plan);
                }
                if (sent && panel.state.conversationId) {
                    panel.state.historyView = false;
                    saveRecentActiveChat(sessionStorage, panel.state.conversationId);
                }
                return sent;
            },
            async decide(decision) {
                if (recoveryPending()) {
                    return false;
                }
                const decided = await panel.decide(decision);
                if (decided) {
                    if (panel.state.actionReceipt?.state === "rejected") {
                        clearRecovery();
                    } else {
                        syncRecoveryFromPlan(panel.state.result?.plan);
                    }
                }
                return decided;
            },
            async retry() {
                if (!recoveryPending()) {
                    return false;
                }
                const restored = await restoreRecovery();
                const state = panel.state.result?.plan?.state;
                if (state === "executing") {
                    return restored;
                }
                if (state !== "authorized") {
                    return restored;
                }
                const retried = await panel.retry();
                if (retried) {
                    syncRecoveryFromPlan(panel.state.result?.plan);
                }
                return retried;
            },
        };
    },
});