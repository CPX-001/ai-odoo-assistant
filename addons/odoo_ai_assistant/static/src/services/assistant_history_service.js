/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

export const ACTIVE_CHAT_TTL_MS = 30 * 60 * 1000;
const ACTIVE_CHAT_CACHE_VERSION = 1;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function browserSessionStorage() {
    try {
        return globalThis.sessionStorage || null;
    } catch {
        return null;
    }
}

export function activeChatStorageKey() {
    const host = globalThis.location?.host || "odoo";
    const uid =
        globalThis.odoo?.session_info?.uid ??
        globalThis.odoo?.__session_info__?.uid;
    const userScope = Number.isSafeInteger(uid) && uid > 0 ? String(uid) : "session";
    return `odoo_ai_assistant:active_chat:${host}:${userScope}`;
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

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        const sessionStorage = browserSessionStorage();
        const initialConversationId = loadRecentActiveChat(sessionStorage);
        panel.state.conversationId = initialConversationId;
        panel.state.historyView = !initialConversationId;

        const recoveryPending = () => panel.state.result?.plan?.state === "authorized";
        const isBusy = () =>
            panel.state.loading ||
            panel.state.historyLoading ||
            panel.state.decisionLoading ||
            recoveryPending();

        const showHistory = async () => {
            if (isBusy()) {
                return false;
            }
            clearRecentActiveChat(sessionStorage);
            panel.newConversation();
            panel.state.historyView = true;
            return panel.loadHistory(null);
        };

        const open = () => {
            panel.state.isOpen = true;
            panel.refreshContext();
            if (recoveryPending()) {
                return;
            }
            const recentConversationId = loadRecentActiveChat(sessionStorage);
            if (!recentConversationId) {
                panel.newConversation();
                panel.state.historyView = true;
                void panel.loadHistory(null);
                return;
            }

            panel.state.conversationId = recentConversationId;
            panel.state.historyView = false;
            void panel.loadHistory(recentConversationId).then((loaded) => {
                if (loaded) {
                    saveRecentActiveChat(sessionStorage, panel.state.conversationId);
                    return;
                }
                void showHistory();
            });
        };

        return {
            ...panel,
            open,
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
                const sent = await panel.submit(message);
                if (sent && panel.state.conversationId) {
                    panel.state.historyView = false;
                    saveRecentActiveChat(sessionStorage, panel.state.conversationId);
                }
                return sent;
            },
        };
    },
});
