/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import { semanticActivityPresentation } from "@odoo_ai_assistant/services/assistant_semantic_activity";

function durationLabel(milliseconds) {
    const ms = Number.isFinite(milliseconds) ? Math.max(0, milliseconds) : 0;
    if (ms < 1000) {
        return "<1 s";
    }
    const seconds = Math.max(1, Math.round(ms / 1000));
    if (seconds < 60) {
        return `${seconds} s`;
    }
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return remainder ? `${minutes} min ${remainder} s` : `${minutes} min`;
}

patch(AssistantPanel.prototype, {
    get semanticActivity() {
        return semanticActivityPresentation(this.state.activityEvents, {
            running: Boolean(this.state.loading),
        });
    },

    get activityItems() {
        return this.semanticActivity.items;
    },

    get activitySummaryLabel() {
        const activity = this.semanticActivity;
        if (this.state.loading) {
            return activity.headline?.label || "Pensando…";
        }
        if (!activity.step_count) {
            return "";
        }
        const steps = activity.step_count === 1 ? "1 paso" : `${activity.step_count} pasos`;
        return `Ha pensado durante ${durationLabel(activity.duration_ms)} · ${steps}`;
    },
});
