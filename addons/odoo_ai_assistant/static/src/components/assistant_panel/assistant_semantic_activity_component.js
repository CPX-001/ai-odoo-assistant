/** @odoo-module **/

import { useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import {
    openPublicReference,
    referenceDisclosure,
    resourceReferences,
} from "@odoo_ai_assistant/services/assistant_public_reference_service";
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

function activeReasoningScope(state) {
    const scoped = state.turnScopes?.[state.activeTurnScopeKey];
    if (scoped) {
        return scoped;
    }
    return {
        turnId: state.turnId || null,
        reasoningSummaryTurnId: state.reasoningSummaryTurnId || null,
        reasoningSummaryParts: state.reasoningSummaryParts || [],
    };
}

function visibleReasoningParts(state, preferences) {
    if (preferences?.reasoning_summary === "off") {
        return [];
    }
    const scope = activeReasoningScope(state);
    if (
        !scope?.turnId ||
        scope.reasoningSummaryTurnId !== scope.turnId ||
        !Array.isArray(scope.reasoningSummaryParts)
    ) {
        return [];
    }
    const serverLimit = Number.isSafeInteger(preferences?.limits?.max_reasoning_summary_chars)
        ? preferences.limits.max_reasoning_summary_chars
        : 2000;
    const maximum =
        preferences.reasoning_summary === "concise" ? Math.min(serverLimit, 600) : serverLimit;
    const result = [];
    let remaining = Math.max(0, maximum);
    for (const part of scope.reasoningSummaryParts) {
        if (!remaining || typeof part?.text !== "string" || !part.text) {
            continue;
        }
        const text = part.text.slice(0, remaining);
        if (text) {
            result.push({ key: part.key, text });
            remaining -= text.length;
        }
    }
    return result;
}

patch(AssistantPanel.prototype, {
    setup() {
        super.setup(...arguments);
        this.semanticReferenceUi = useState({ visibleByKey: {} });
    },

    get semanticActivity() {
        return semanticActivityPresentation(this.state.activityEvents, {
            running: Boolean(this.state.loading),
            preferences: this.state.activityPresentation,
        });
    },

    get activityItems() {
        const activity = this.semanticActivity;
        return activity.items.map((item) => {
            const references = resourceReferences(item.resource);
            const disclosure = referenceDisclosure(references, {
                pageSize: activity.preferences.batch_page_size,
                visibleCount: this.semanticReferenceUi.visibleByKey[item.key] || null,
            });
            return {
                ...item,
                display_label: `${semanticLabel(item)}${technicalSuffix(item, activity.preferences)}`,
                duration_label:
                    activity.preferences.show_step_durations && item.duration_ms !== null
                        ? durationLabel(item.duration_ms)
                        : "",
                references: disclosure.visible,
                reference_remaining_count: disclosure.remaining_count,
                reference_next_count: disclosure.next_count,
                can_show_more_references: disclosure.can_show_more,
            };
        });
    },

    get activityReasoningSummaryParts() {
        return visibleReasoningParts(this.state, this.semanticActivity.preferences);
    },

    get activityReasoningSummaryTitle() {
        return _t("Resumen del razonamiento");
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

    activityShowMoreLabel(item) {
        if (!item?.reference_next_count) {
            return "";
        }
        if (item.reference_remaining_count === item.reference_next_count) {
            return _t("Mostrar los %s restantes", item.reference_remaining_count);
        }
        return _t("Mostrar %s más", item.reference_next_count);
    },

    showMoreActivityReferences(item) {
        if (!item?.key || !item.reference_next_count) {
            return;
        }
        const current = this.semanticReferenceUi.visibleByKey[item.key] ||
            this.semanticActivity.preferences.batch_page_size;
        const maximum = this.semanticActivity.preferences.limits.max_rendered_batch_rows;
        this.semanticReferenceUi.visibleByKey[item.key] = Math.min(
            maximum,
            current + item.reference_next_count
        );
    },

    async openActivityReference(reference) {
        return openPublicReference(reference, { actionService: this.actionService });
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

export { durationLabel, semanticLabel, visibleReasoningParts };
