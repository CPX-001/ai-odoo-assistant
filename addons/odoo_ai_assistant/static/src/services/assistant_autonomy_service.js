/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

export const AUTONOMY_PROFILES = Object.freeze([
    "strict",
    "balanced",
    "autonomous",
    "full_access",
]);

export function normalizeAutonomyResponse(response) {
    if (
        response?.ok !== true ||
        typeof response.profile !== "string" ||
        !AUTONOMY_PROFILES.includes(response.profile)
    ) {
        return null;
    }
    return response.profile;
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        panel.state.autonomyProfile = "balanced";
        panel.state.autonomyLoading = false;
        panel.state.autonomySaving = false;
        panel.state.autonomyLoaded = false;

        const loadAutonomyProfile = async ({ force = false } = {}) => {
            if (panel.state.autonomyLoading || (panel.state.autonomyLoaded && !force)) {
                return panel.state.autonomyLoaded;
            }
            panel.state.autonomyLoading = true;
            try {
                const profile = normalizeAutonomyResponse(
                    await rpc("/odoo_ai/v1/agent-autonomy", {})
                );
                if (!profile) {
                    return false;
                }
                panel.state.autonomyProfile = profile;
                panel.state.autonomyLoaded = true;
                return true;
            } catch {
                return false;
            } finally {
                panel.state.autonomyLoading = false;
            }
        };

        const setAutonomyProfile = async (profile) => {
            if (panel.state.autonomySaving || !AUTONOMY_PROFILES.includes(profile)) {
                return false;
            }
            panel.state.autonomySaving = true;
            try {
                const selected = normalizeAutonomyResponse(
                    await rpc("/odoo_ai/v1/agent-autonomy-set", { profile })
                );
                if (!selected) {
                    return false;
                }
                panel.state.autonomyProfile = selected;
                panel.state.autonomyLoaded = true;
                return true;
            } catch {
                return false;
            } finally {
                panel.state.autonomySaving = false;
            }
        };

        // Load once when the web client service starts. This avoids depending on the
        // order in which other frontend patches wrap open()/toggle().
        void loadAutonomyProfile();

        return {
            ...panel,
            loadAutonomyProfile,
            setAutonomyProfile,
        };
    },
});
