/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";
import {
    DEFAULT_ACTIVITY_PRESENTATION,
    normalizeActivityPresentationPreferences,
} from "@odoo_ai_assistant/services/assistant_semantic_activity";

const DETAIL_LEVELS = new Set(["compact", "normal", "detailed", "diagnostic"]);
const REASONING_SUMMARY_LEVELS = new Set(["off", "concise", "detailed"]);

function normalizeServerPreferences(response) {
    if (
        response?.ok !== true ||
        !DETAIL_LEVELS.has(response.detail_level) ||
        !Number.isSafeInteger(response.transient_threshold_ms) ||
        response.transient_threshold_ms < 0 ||
        response.transient_threshold_ms > 5000 ||
        !Number.isSafeInteger(response.batch_page_size) ||
        response.batch_page_size < 1 ||
        response.batch_page_size > 20 ||
        typeof response.show_technical_names !== "boolean" ||
        typeof response.show_step_durations !== "boolean" ||
        !REASONING_SUMMARY_LEVELS.has(response.reasoning_summary) ||
        response.limits === null ||
        typeof response.limits !== "object"
    ) {
        return null;
    }
    return normalizeActivityPresentationPreferences(response);
}

function validPreferencePatch(values) {
    if (values === null || typeof values !== "object" || Array.isArray(values)) {
        return false;
    }
    const keys = Object.keys(values);
    const allowed = new Set([
        "detail_level",
        "transient_threshold_ms",
        "batch_page_size",
        "show_technical_names",
        "show_step_durations",
        "reasoning_summary",
    ]);
    if (!keys.length || keys.some((key) => !allowed.has(key))) {
        return false;
    }
    if (Object.hasOwn(values, "detail_level") && !DETAIL_LEVELS.has(values.detail_level)) {
        return false;
    }
    if (
        Object.hasOwn(values, "transient_threshold_ms") &&
        (!Number.isSafeInteger(values.transient_threshold_ms) ||
            values.transient_threshold_ms < 0 ||
            values.transient_threshold_ms > 5000)
    ) {
        return false;
    }
    if (
        Object.hasOwn(values, "batch_page_size") &&
        (!Number.isSafeInteger(values.batch_page_size) ||
            values.batch_page_size < 1 ||
            values.batch_page_size > 20)
    ) {
        return false;
    }
    for (const key of ["show_technical_names", "show_step_durations"]) {
        if (Object.hasOwn(values, key) && typeof values[key] !== "boolean") {
            return false;
        }
    }
    return !Object.hasOwn(values, "reasoning_summary") || REASONING_SUMMARY_LEVELS.has(values.reasoning_summary);
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        panel.state.activityPresentation = { ...DEFAULT_ACTIVITY_PRESENTATION };
        panel.state.activityPreferencesLoading = false;
        panel.state.activityPreferencesSaving = false;

        const loadActivityPresentationPreferences = async () => {
            if (panel.state.activityPreferencesLoading) {
                return false;
            }
            panel.state.activityPreferencesLoading = true;
            try {
                const response = await rpc("/odoo_ai/v1/activity-preferences", {});
                const normalized = normalizeServerPreferences(response);
                if (!normalized) {
                    return false;
                }
                panel.state.activityPresentation = normalized;
                return true;
            } catch {
                return false;
            } finally {
                panel.state.activityPreferencesLoading = false;
            }
        };

        const setActivityPresentationPreferences = async (values) => {
            if (panel.state.activityPreferencesSaving || !validPreferencePatch(values)) {
                return false;
            }
            panel.state.activityPreferencesSaving = true;
            try {
                const response = await rpc("/odoo_ai/v1/activity-preferences-set", {
                    preferences: values,
                });
                const normalized = normalizeServerPreferences(response);
                if (!normalized) {
                    return false;
                }
                panel.state.activityPresentation = normalized;
                return true;
            } catch {
                return false;
            } finally {
                panel.state.activityPreferencesSaving = false;
            }
        };

        void loadActivityPresentationPreferences();

        return {
            ...panel,
            loadActivityPresentationPreferences,
            setActivityPresentationPreferences,
        };
    },
});

export { normalizeServerPreferences, validPreferencePatch };
