/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
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

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        panel.state.planningMode = "adaptive";
        panel.state.planningLoading = false;
        panel.state.planningSaving = false;
        panel.state.planningLoaded = false;

        const loadPlanningMode = async ({ force = false } = {}) => {
            if (panel.state.planningLoading || (panel.state.planningLoaded && !force)) {
                return panel.state.planningLoaded;
            }
            panel.state.planningLoading = true;
            try {
                const mode = normalizePlanningModeResponse(
                    await rpc("/odoo_ai/v1/planning-mode", {})
                );
                if (!mode) {
                    return false;
                }
                panel.state.planningMode = mode;
                panel.state.planningLoaded = true;
                return true;
            } catch {
                return false;
            } finally {
                panel.state.planningLoading = false;
            }
        };

        const setPlanningMode = async (mode) => {
            if (panel.state.planningSaving || !PLANNING_MODES.includes(mode)) {
                return false;
            }
            panel.state.planningSaving = true;
            try {
                const selected = normalizePlanningModeResponse(
                    await rpc("/odoo_ai/v1/planning-mode-set", { mode })
                );
                if (!selected) {
                    return false;
                }
                panel.state.planningMode = selected;
                panel.state.planningLoaded = true;
                return true;
            } catch {
                return false;
            } finally {
                panel.state.planningSaving = false;
            }
        };

        void loadPlanningMode();

        return {
            ...panel,
            loadPlanningMode,
            setPlanningMode,
        };
    },
});