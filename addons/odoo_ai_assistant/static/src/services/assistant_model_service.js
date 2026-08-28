/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

const MODEL_PATTERN = /^[A-Za-z0-9_.:-]{1,128}$/;
const MODEL_CATALOG_TTL_MS = 5 * 60 * 1000;

export function compactModelLabel(value) {
    if (typeof value !== "string" || !value.trim()) {
        return "Predeterminado";
    }
    return value
        .trim()
        .replace(/^gpt[- ]?/i, "")
        .replace(/[-_:/]+/g, " ")
        .replace(/\bcodex\b/gi, "Codex")
        .replace(/\bsol\b/gi, "Sol")
        .replace(/\s+/g, " ");
}

export function normalizeModelPreferences(response) {
    if (
        response?.ok !== true ||
        !Array.isArray(response.models) ||
        response.models.length > 50 ||
        !response.models.every(
            (item) =>
                item !== null &&
                typeof item === "object" &&
                MODEL_PATTERN.test(item.model) &&
                typeof item.display_name === "string" &&
                item.display_name.length > 0 &&
                item.display_name.length <= 160 &&
                typeof item.is_default === "boolean"
        ) ||
        (response.default_model !== null && !MODEL_PATTERN.test(response.default_model)) ||
        (response.selected_model !== null && !MODEL_PATTERN.test(response.selected_model)) ||
        typeof response.can_manage_settings !== "boolean"
    ) {
        return null;
    }
    const ids = new Set(response.models.map((item) => item.model));
    if (ids.size !== response.models.length) {
        return null;
    }
    return {
        models: response.models.map((item) => ({ ...item })),
        defaultModel: response.default_model,
        selectedModel: ids.has(response.selected_model) ? response.selected_model : null,
        canManageSettings: response.can_manage_settings,
    };
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        panel.state.modelOptions = [];
        panel.state.defaultReasoningModel = null;
        panel.state.selectedReasoningModel = null;
        panel.state.modelLoading = false;
        panel.state.modelSaving = false;
        panel.state.modelCatalogLoadedAt = 0;
        panel.state.canManageAssistantSettings = false;

        const loadModelPreferences = async ({ force = false } = {}) => {
            if (panel.state.modelLoading) {
                return false;
            }
            const now = Date.now();
            if (
                !force &&
                panel.state.modelCatalogLoadedAt > 0 &&
                now - panel.state.modelCatalogLoadedAt < MODEL_CATALOG_TTL_MS
            ) {
                return true;
            }
            panel.state.modelLoading = true;
            try {
                const response = await rpc("/odoo_ai/v1/chat-models", {});
                const normalized = normalizeModelPreferences(response);
                if (!normalized) {
                    return false;
                }
                panel.state.modelOptions = normalized.models;
                panel.state.defaultReasoningModel = normalized.defaultModel;
                panel.state.selectedReasoningModel = normalized.selectedModel;
                panel.state.canManageAssistantSettings = normalized.canManageSettings;
                panel.state.modelCatalogLoadedAt = now;
                return true;
            } catch {
                return false;
            } finally {
                panel.state.modelLoading = false;
            }
        };

        const setReasoningModel = async (model) => {
            const normalized = model || null;
            if (
                panel.state.modelSaving ||
                (normalized !== null &&
                    !panel.state.modelOptions.some((item) => item.model === normalized))
            ) {
                return false;
            }
            panel.state.modelSaving = true;
            try {
                const response = await rpc("/odoo_ai/v1/chat-model", { model: normalized });
                if (
                    response?.ok !== true ||
                    (response.selected_model !== null &&
                        !MODEL_PATTERN.test(response.selected_model))
                ) {
                    return false;
                }
                panel.state.selectedReasoningModel = response.selected_model;
                return true;
            } catch {
                return false;
            } finally {
                panel.state.modelSaving = false;
            }
        };

        // Load once when the web-client service starts. P5 turn-scope patches may
        // replace open()/toggle(), so picker readiness must not depend solely on
        // wrapper order. Later opens still use the bounded catalog TTL.
        void loadModelPreferences();

        const baseOpen = panel.open.bind(panel);
        const baseToggle = panel.toggle.bind(panel);

        return {
            ...panel,
            open() {
                baseOpen();
                void loadModelPreferences();
            },
            toggle() {
                const wasOpen = panel.state.isOpen;
                baseToggle();
                if (!wasOpen && panel.state.isOpen) {
                    void loadModelPreferences();
                }
            },
            loadModelPreferences,
            setReasoningModel,
        };
    },
});
