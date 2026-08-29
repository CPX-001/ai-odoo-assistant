/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import { semanticActivityPresentation } from "@odoo_ai_assistant/services/assistant_semantic_activity";

function durationLabel(milliseconds) {
    const ms = Number.isFinite(milliseconds) ? Math.max(0, milliseconds) : 0;
    if (ms < 1000) {
        return _t("<1 s");
    }
    const seconds = Math.max(1, Math.round(ms / 1000));
    if (seconds < 60) {
        return _t("%s s", seconds);
    }
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return remainder ? _t("%s min %s s", minutes, remainder) : _t("%s min", minutes);
}

function semanticLabel(item) {
    if (!item) {
        return _t("Trabajando en Odoo");
    }
    switch (item.semantic_code) {
        case "request.analysis":
            return _t("Analizando la petición");
        case "answer.compose":
            return _t("Redactando respuesta");
        case "evidence.search":
            return _t("Buscando información");
        case "capability.prepare":
            return _t("Preparando cambios");
        case "approval.wait":
            return _t("Esperando aprobación");
        case "capability.execute":
            return _t("Ejecutando cambios");
        case "capability.verify":
            return _t("Verificando resultados");
        case "capability.use":
            return _t("Consultando Odoo");
        case "activity.failed":
            return _t("La operación ha fallado");
        case "activity.blocked":
            return _t("La operación está bloqueada");
        case "queue.wait":
            return _t("Esperando turno");
        case "turn.finalize":
            return _t("Finalizando");
        default:
            return _t("Trabajando en Odoo");
    }
}

function technicalSuffix(item, preferences) {
    if (!preferences?.show_technical_names || !item) {
        return "";
    }
    const technical = [];
    if (item.capability) {
        technical.push(item.capability);
    }
    if (item.resource?.model && !technical.includes(item.resource.model)) {
        technical.push(item.resource.model);
    }
    if (!technical.length && item.label) {
        technical.push(item.label);
    }
    return technical.length ? ` · ${technical.join(" · ")}` : "";
}

patch(AssistantPanel.prototype, {
    get semanticActivity() {
        return semanticActivityPresentation(this.state.activityEvents, {
            running: Boolean(this.state.loading),
            preferences: this.state.activityPresentation,
        });
    },

    get activityItems() {
        const activity = this.semanticActivity;
        return activity.items.map((item) => ({
            ...item,
            display_label: `${semanticLabel(item)}${technicalSuffix(item, activity.preferences)}`,
            duration_label:
                activity.preferences.show_step_durations && item.duration_ms !== null
                    ? durationLabel(item.duration_ms)
                    : "",
        }));
    },

    get activitySummaryLabel() {
        const activity = this.semanticActivity;
        if (this.state.loading) {
            return _t("Razonando · %s", semanticLabel(activity.headline));
        }
        if (!activity.step_count) {
            return "";
        }
        const duration = durationLabel(activity.duration_ms);
        if (activity.step_count === 1) {
            return _t("Ha pensado durante %s · 1 paso", duration);
        }
        return _t("Ha pensado durante %s · %s pasos", duration, activity.step_count);
    },

    get activityDetailLevel() {
        return this.semanticActivity.preferences.detail_level;
    },

    get activityReasoningSummaryLevel() {
        return this.semanticActivity.preferences.reasoning_summary;
    },

    async changeActivityDetailLevel(event) {
        const detailLevel = event?.target?.value;
        if (typeof this.panel.setActivityPresentationPreferences === "function") {
            await this.panel.setActivityPresentationPreferences({ detail_level: detailLevel });
        }
    },

    async changeActivityReasoningSummary(event) {
        const reasoningSummary = event?.target?.value;
        if (typeof this.panel.setActivityPresentationPreferences === "function") {
            await this.panel.setActivityPresentationPreferences({ reasoning_summary: reasoningSummary });
        }
    },

    async toggleActivityTechnicalNames() {
        if (typeof this.panel.setActivityPresentationPreferences === "function") {
            await this.panel.setActivityPresentationPreferences({
                show_technical_names: !this.semanticActivity.preferences.show_technical_names,
            });
        }
    },
});

export { durationLabel, semanticLabel };
