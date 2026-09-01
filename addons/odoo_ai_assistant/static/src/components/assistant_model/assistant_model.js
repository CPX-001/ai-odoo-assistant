/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import {
    AUTO_REASONING_EFFORT,
    compactModelLabel,
    groupModelOptions,
    modelFamilyLabel,
    pickerReasoningEfforts,
    supportsAutoReasoning,
} from "@odoo_ai_assistant/services/assistant_model_service";

function reasoningEffortLabel(effort) {
    const labels = {
        auto: _t("Auto"),
        none: _t("Ninguno"),
        minimal: _t("Mínimo"),
        low: _t("Bajo"),
        medium: _t("Medio"),
        high: _t("Alto"),
        xhigh: _t("Muy alto"),
        max: _t("Máximo"),
    };
    return labels[effort] || effort || _t("Predeterminado");
}

function reasoningEffortDescription(effort, providerDescription = "") {
    const descriptions = {
        auto: _t("Ajusta el esfuerzo por decisión según la complejidad y el progreso real."),
        none: _t("Prioriza la velocidad y evita razonamiento adicional."),
        minimal: _t("Usa el mínimo razonamiento adicional."),
        low: _t("Razonamiento ligero para tareas sencillas."),
        medium: _t("Equilibrio entre calidad y velocidad."),
        high: _t("Más razonamiento para tareas complejas."),
    };
    return descriptions[effort] || providerDescription;
}

function variantLabel(option) {
    const variant = option?.variant;
    if (variant === "sol") return "Sol";
    if (variant === "terra") return "Terra";
    if (variant === "luna") return "Luna";
    return compactModelLabel(option?.display_name || option?.model) || option?.model || "";
}

function variantDescription(option) {
    const descriptions = {
        sol: _t("Máxima capacidad"),
        terra: _t("Equilibrio entre capacidad y coste"),
        luna: _t("Rápido y económico"),
    };
    return descriptions[option?.variant] || option?.description || "";
}

function modelPillLabel(option, fallback = "") {
    const variants = { sol: "S", terra: "T", luna: "L" };
    if (variants[option?.variant]) {
        return variants[option.variant];
    }
    const compact = compactModelLabel(option?.family || option?.display_name || fallback);
    return compact.replace(/\s+mini$/i, "m").replace(/\s+/g, "").slice(0, 6) || "M";
}

function reasoningEffortPillLabel(effort) {
    const labels = { auto: "A", none: "0", minimal: "1", low: "2", medium: "3", high: "4" };
    return labels[effort] || "R";
}

patch(AssistantPanel.prototype, {
    get reasoningModelOption() {
        const target = this.state.selectedReasoningModel || this.state.defaultReasoningModel;
        return this.state.modelOptions.find((item) => item.model === target) || null;
    },

    get reasoningModelLabel() {
        return (
            this.reasoningModelOption?.display_name ||
            this.state.defaultReasoningModel ||
            _t("Predeterminado")
        );
    },

    get reasoningModelCompactLabel() {
        const family = this.reasoningModelOption?.family;
        return family
            ? modelFamilyLabel(family)
            : compactModelLabel(this.reasoningModelLabel) || _t("Predeterminado");
    },

    get reasoningModelPillLabel() {
        return modelPillLabel(this.reasoningModelOption, this.state.defaultReasoningModel);
    },

    get reasoningModelGroups() {
        return groupModelOptions(this.state.modelOptions);
    },

    get defaultReasoningModelLabel() {
        const option = this.state.modelOptions.find(
            (item) => item.model === this.state.defaultReasoningModel
        );
        return option?.family
            ? modelFamilyLabel(option.family)
            : compactModelLabel(option?.display_name || this.state.defaultReasoningModel);
    },

    get reasoningEffortOptions() {
        const options = this.reasoningModelOption?.supported_reasoning_efforts;
        return pickerReasoningEfforts(options);
    },

    get reasoningAutoAvailable() {
        return supportsAutoReasoning(this.reasoningModelOption);
    },

    get defaultReasoningEffort() {
        return this.reasoningModelOption?.default_reasoning_effort || null;
    },

    get defaultReasoningEffortLabel() {
        return this.defaultReasoningEffort
            ? reasoningEffortLabel(this.defaultReasoningEffort)
            : "";
    },

    get reasoningEffortCompactLabel() {
        return reasoningEffortLabel(
            this.state.selectedReasoningEffort || this.defaultReasoningEffort
        );
    },

    get reasoningEffortPillLabel() {
        return reasoningEffortPillLabel(
            this.state.selectedReasoningEffort || this.defaultReasoningEffort
        );
    },

    get reasoningEffortTitle() {
        const selected = this.state.selectedReasoningEffort;
        if (selected) {
            return _t("Nivel de razonamiento: %s", reasoningEffortLabel(selected));
        }
        if (this.defaultReasoningEffort) {
            return _t(
                "Nivel de razonamiento: %s (predeterminado)",
                reasoningEffortLabel(this.defaultReasoningEffort)
            );
        }
        return _t("Nivel de razonamiento");
    },

    modelVariantLabel(option) {
        return variantLabel(option);
    },

    modelVariantDescription(option) {
        return variantDescription(option);
    },

    modelOptionPillLabel(option) {
        return modelPillLabel(option);
    },

    reasoningEffortOptionLabel(option) {
        return reasoningEffortLabel(option?.effort);
    },

    reasoningEffortOptionDescription(option) {
        return reasoningEffortDescription(option?.effort, option?.description || "");
    },

    reasoningEffortOptionPillLabel(option) {
        return reasoningEffortPillLabel(option?.effort);
    },

    autoReasoningEffortLabel() {
        return reasoningEffortLabel(AUTO_REASONING_EFFORT);
    },

    autoReasoningEffortDescription() {
        return reasoningEffortDescription(AUTO_REASONING_EFFORT);
    },

    isReasoningModelSelected(option) {
        if (!option || !this.state.selectedReasoningModel) {
            return false;
        }
        if (option.model === this.state.selectedReasoningModel) {
            return true;
        }
        const selected = this.state.modelOptions.find(
            (item) => item.model === this.state.selectedReasoningModel
        );
        return Boolean(
            selected?.family === option.family &&
                selected?.variant &&
                selected.variant === option.variant
        );
    },

    isReasoningFamilySelected(group) {
        return Boolean(
            this.state.selectedReasoningModel &&
                this.state.modelOptions.some(
                    (item) =>
                        item.model === this.state.selectedReasoningModel &&
                        item.family === group.family
                )
        );
    },

    async selectReasoningModel(model) {
        await this.panel.setReasoningModel(model || null);
    },

    async selectReasoningEffort(effort) {
        await this.panel.setReasoningEffort(effort || null);
    },

    async selectAutoReasoningEffort() {
        await this.panel.setReasoningEffort(AUTO_REASONING_EFFORT);
    },

    async retryModelPreferences() {
        await this.panel.loadModelPreferences({ force: true });
    },

    async openAssistantSettings() {
        this.panel.close();
        await this.actionService.doAction("base_setup.action_general_configuration", {
            additionalContext: { module: "odoo_ai_assistant" },
        });
    },
});
