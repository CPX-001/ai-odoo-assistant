/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

import { AssistantPanel } from "./assistant_panel";

function safeLoginUrl(value) {
    if (typeof value !== "string" || !value) {
        return null;
    }
    try {
        const url = new URL(value);
        const host = url.hostname.toLowerCase();
        const trusted =
            host === "chatgpt.com" ||
            host.endsWith(".chatgpt.com") ||
            host === "openai.com" ||
            host.endsWith(".openai.com");
        return url.protocol === "https:" && trusted ? url.href : null;
    } catch {
        return null;
    }
}

patch(AssistantPanel.prototype, {
    stopRuntimeMenuPointerDown(ev) {
        ev?.stopPropagation?.();
    },

    toggleRuntimeAccountMenu(ev) {
        ev?.preventDefault?.();
        ev?.stopPropagation?.();
        this.ui.accountOpen = !this.ui.accountOpen;
    },

    openRuntimeSettings(ev) {
        ev?.preventDefault?.();
        ev?.stopPropagation?.();
        this.ui.accountOpen = false;
        return this.openAssistantSettings();
    },

    async connectRuntimeAccount(ev) {
        ev?.preventDefault?.();
        ev?.stopPropagation?.();
        this.ui.accountOpen = false;
        return this.panel.connectRuntimeAccount();
    },

    async refreshRuntimeAccount(ev) {
        ev?.preventDefault?.();
        ev?.stopPropagation?.();
        return this.panel.refreshRuntimeAccount();
    },

    async cancelRuntimeLogin(ev) {
        ev?.preventDefault?.();
        ev?.stopPropagation?.();
        return this.panel.cancelRuntimeLogin();
    },

    async logoutRuntimeAccount(ev) {
        ev?.preventDefault?.();
        ev?.stopPropagation?.();
        this.ui.accountOpen = false;
        return this.panel.logoutRuntimeAccount();
    },

    openRuntimeLoginPage(ev) {
        ev?.preventDefault?.();
        ev?.stopPropagation?.();
        const url = safeLoginUrl(this.state.runtimeVerificationUrl);
        if (!url) {
            return false;
        }
        globalThis.open?.(url, "_blank", "noopener,noreferrer");
        return true;
    },

    runtimeUsageLabel(row) {
        if (!row || typeof row !== "object") {
            return "";
        }
        const name = row.limit_name || row.limit_id || _t("Límite Codex");
        const used =
            typeof row.used_percent === "number" && Number.isFinite(row.used_percent)
                ? `${Math.round(row.used_percent)}%`
                : null;
        const duration =
            Number.isSafeInteger(row.window_duration_mins) && row.window_duration_mins > 0
                ? `${row.window_duration_mins} min`
                : row.window || null;
        return [name, used, duration].filter(Boolean).join(" · ");
    },
});
