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

export function runtimeUsageWindowLabel(row) {
    const duration = row?.window_duration_mins;
    if (duration === 300) {
        return _t("5 horas");
    }
    if (duration === 10080) {
        return _t("Semanal");
    }
    if (row?.window === "primary") {
        return _t("Ventana principal");
    }
    if (row?.window === "secondary") {
        return _t("Ventana secundaria");
    }
    return null;
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
        const window = runtimeUsageWindowLabel(row);
        const used =
            typeof row.used_percent === "number" && Number.isFinite(row.used_percent)
                ? _t("%s usado", `${Math.round(row.used_percent)}%`)
                : null;
        return [name, window, used].filter(Boolean).join(" · ");
    },
});
