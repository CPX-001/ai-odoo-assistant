/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

export const PLANNING_MODES = Object.freeze(["adaptive", "deliberate"]);

export function normalizePlanningModeResponse(response) {
    if (
        response?.ok !== true ||
        typeof response.mode !== "string" ||
        !PLANNING_MODES.includes(response.mode)
    ) {
        return null;
    }
    return response.mode;
}

export function planningModeAfterSubmit(mode, sent) {
    if (!PLANNING_MODES.includes(mode)) {
        return "adaptive";
    }
    return sent && mode === "deliberate" ? "adaptive" : mode;
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        panel.state.planningMode = "adaptive";
        panel.state.planningLoading = false;
        panel.state.planningSaving = false;
        panel.state.planningLoaded = true;

        const setPlanningMode = async (mode) => {
            if (!PLANNING_MODES.includes(mode)) {
                return false;
            }
            panel.state.planningMode = mode;
            return true;
        };

        const submit = panel.submit.bind(panel);
        const submitOneShot = async (message) => {
            const selected = panel.state.planningMode;
            const sent = await submit(message);
            // The streaming path consumes Plan as soon as Odoo durably accepts the turn.  Only
            // apply the fallback transition when the underlying submit path did not already move
            // the one-shot state, so a later stream failure cannot resurrect consumed Plan.
            if (panel.state.planningMode === selected) {
                panel.state.planningMode = planningModeAfterSubmit(selected, sent);
            }
            return sent;
        };

        return {
            ...panel,
            loadPlanningMode: async () => true,
            setPlanningMode,
            submit: submitOneShot,
        };
    },
});