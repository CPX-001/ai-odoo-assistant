/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

const MODEL_PATTERN = /^[A-Za-z0-9_.:-]{1,128}$/;
const EFFORT_PATTERN = /^[a-z][a-z0-9_-]{0,31}$/;
const MODEL_CATALOG_TTL_MS = 5 * 60 * 1000;
const VARIANT_ORDER = Object.freeze({ sol: 0, terra: 1, luna: 2 });
const PICKER_REASONING_EFFORTS = new Set(["none", "minimal", "low", "medium", "high"]);

export function compactModelLabel(value) {
    if (typeof value !== "string" || !value.trim()) {
        return "";
    }
    return value
        .trim()
        .replace(/^gpt[- ]?/i, "")
        .replace(/[-_:/]+/g, " ")
        .replace(/\bcodex\b/gi, "Codex")
        .replace(/\bsol\b/gi, "Sol")
        .replace(/\bterra\b/gi, "Terra")
        .replace(/\bluna\b/gi, "Luna")
        .replace(/\s+/g, " ");
}

export function modelFamilyLabel(value) {
    if (typeof value !== "string" || !value.trim()) {
        return "";
    }
    const normalized = value.trim();
    const match = /^gpt[- ]?(.+)$/i.exec(normalized);
    return match ? `GPT-${match[1]}` : normalized;
}

export function groupModelOptions(models) {
    if (!Array.isArray(models)) {
        return [];
    }
    const groups = [];
    const byFamily = new Map();
    for (const model of models) {
        const family = model.family || model.model;
        let group = byFamily.get(family);
        if (!group) {
            group = { family, label: modelFamilyLabel(family), models: [] };
            byFamily.set(family, group);
            groups.push(group);
        }
        group.models.push(model);
    }
    return groups.map((group) => {
        const variants = new Map();
        const ungrouped = [];
        for (const model of group.models) {
            if (!model.variant) {
                ungrouped.push(model);
                continue;
            }
            const existing = variants.get(model.variant);
            if (!existing || (existing.family_alias && !model.family_alias)) {
                variants.set(model.variant, model);
            }
        }
        const groupedVariants = [...variants.values()].sort((left, right) => {
            const leftRank = VARIANT_ORDER[left.variant] ?? 100;
            const rightRank = VARIANT_ORDER[right.variant] ?? 100;
            return leftRank - rightRank || left.display_name.localeCompare(right.display_name);
        });
        const displayModels = [...groupedVariants, ...ungrouped];
        return {
            ...group,
            models: displayModels,
            hasVariants: groupedVariants.length > 1,
        };
    });
}

export function pickerReasoningEfforts(options) {
    if (!Array.isArray(options)) {
        return [];
    }
    return options.filter((item) => PICKER_REASONING_EFFORTS.has(item?.effort));
}

export function normalizeModelPreferences(response) {
    if (
        response?.ok !== true ||
        !Array.isArray(response.models) ||
        response.models.length > 50 ||
        !response.models.every(_validBaseModel) ||
        (response.default_model !== null && !MODEL_PATTERN.test(response.default_model)) ||
        (response.selected_model !== null && !MODEL_PATTERN.test(response.selected_model)) ||
        (response.selected_reasoning_effort != null &&
            !EFFORT_PATTERN.test(response.selected_reasoning_effort)) ||
        typeof response.can_manage_settings !== "boolean"
    ) {
        return null;
    }
    const models = response.models.map(_normalizeModelOption);
    if (models.some((item) => item === null)) {
        return null;
    }
    const ids = new Set(models.map((item) => item.model));
    if (ids.size !== models.length) {
        return null;
    }
    const selectedModel = ids.has(response.selected_model) ? response.selected_model : null;
    const effectiveModelId = selectedModel || response.default_model;
    const effectiveModel = models.find((item) => item.model === effectiveModelId) || null;
    if (
        response.selected_reasoning_effort != null &&
        effectiveModel?.reasoning_metadata_available &&
        !effectiveModel.supported_reasoning_efforts.some(
            (item) => item.effort === response.selected_reasoning_effort
        )
    ) {
        return null;
    }
    return {
        models,
        defaultModel: response.default_model,
        selectedModel,
        selectedReasoningEffort: response.selected_reasoning_effort || null,
        canManageSettings: response.can_manage_settings,
    };
}

function _validBaseModel(item) {
    return (
        item !== null &&
        typeof item === "object" &&
        MODEL_PATTERN.test(item.model) &&
        typeof item.display_name === "string" &&
        item.display_name.length > 0 &&
        item.display_name.length <= 160 &&
        typeof item.is_default === "boolean"
    );
}

function _normalizeModelOption(item) {
    const family = item.family ?? item.model;
    const variant = item.variant ?? null;
    const description = item.description ?? "";
    const familyAlias = item.family_alias ?? false;
    const defaultEffort = item.default_reasoning_effort ?? null;
    const rawEfforts = item.supported_reasoning_efforts ?? [];
    const reasoningMetadataAvailable = Object.hasOwn(item, "supported_reasoning_efforts");
    if (
        !MODEL_PATTERN.test(family) ||
        (variant !== null && !EFFORT_PATTERN.test(variant)) ||
        typeof description !== "string" ||
        description.length > 512 ||
        typeof familyAlias !== "boolean" ||
        (defaultEffort !== null && !EFFORT_PATTERN.test(defaultEffort)) ||
        !Array.isArray(rawEfforts) ||
        rawEfforts.length > 12
    ) {
        return null;
    }
    const efforts = [];
    const seen = new Set();
    for (const entry of rawEfforts) {
        if (
            entry === null ||
            typeof entry !== "object" ||
            !EFFORT_PATTERN.test(entry.effort) ||
            typeof entry.description !== "string" ||
            entry.description.length > 512 ||
            seen.has(entry.effort)
        ) {
            return null;
        }
        seen.add(entry.effort);
        efforts.push({ effort: entry.effort, description: entry.description });
    }
    if (defaultEffort !== null && !seen.has(defaultEffort)) {
        return null;
    }
    return {
        ...item,
        family,
        variant,
        description,
        family_alias: familyAlias,
        reasoning_metadata_available: reasoningMetadataAvailable,
        supported_reasoning_efforts: efforts,
        default_reasoning_effort: defaultEffort,
    };
}

function _effectiveModelOption(state) {
    const target = state.selectedReasoningModel || state.defaultReasoningModel;
    return state.modelOptions.find((item) => item.model === target) || null;
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        panel.state.modelOptions = [];
        panel.state.defaultReasoningModel = null;
        panel.state.selectedReasoningModel = null;
        panel.state.selectedReasoningEffort = null;
        panel.state.modelLoading = false;
        panel.state.modelSaving = false;
        panel.state.reasoningEffortSaving = false;
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
                panel.state.selectedReasoningEffort = normalized.selectedReasoningEffort;
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
                        !MODEL_PATTERN.test(response.selected_model)) ||
                    (response.selected_reasoning_effort != null &&
                        !EFFORT_PATTERN.test(response.selected_reasoning_effort))
                ) {
                    return false;
                }
                panel.state.selectedReasoningModel = response.selected_model;
                if (Object.hasOwn(response, "selected_reasoning_effort")) {
                    panel.state.selectedReasoningEffort =
                        response.selected_reasoning_effort || null;
                }
                return true;
            } catch {
                return false;
            } finally {
                panel.state.modelSaving = false;
            }
        };

        const setReasoningEffort = async (effort) => {
            const normalized = effort || null;
            const effective = _effectiveModelOption(panel.state);
            const supported = new Set(
                effective?.supported_reasoning_efforts?.map((item) => item.effort) || []
            );
            if (
                panel.state.reasoningEffortSaving ||
                (normalized !== null && (!EFFORT_PATTERN.test(normalized) || !supported.has(normalized)))
            ) {
                return false;
            }
            panel.state.reasoningEffortSaving = true;
            try {
                const response = await rpc("/odoo_ai/v1/chat-reasoning-effort", {
                    effort: normalized,
                });
                if (
                    response?.ok !== true ||
                    (response.selected_reasoning_effort != null &&
                        !EFFORT_PATTERN.test(response.selected_reasoning_effort))
                ) {
                    return false;
                }
                panel.state.selectedReasoningEffort =
                    response.selected_reasoning_effort || null;
                return true;
            } catch {
                return false;
            } finally {
                panel.state.reasoningEffortSaving = false;
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
            setReasoningEffort,
        };
    },
});
