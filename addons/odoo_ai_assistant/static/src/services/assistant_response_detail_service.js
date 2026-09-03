/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

export const RESPONSE_DETAIL_LEVELS = Object.freeze(["concise", "normal", "extensive"]);
const RESPONSE_DETAIL_SET = new Set(RESPONSE_DETAIL_LEVELS);

export function normalizeResponseDetailPreferences(response) {
    if (
        response?.ok !== true ||
        !RESPONSE_DETAIL_SET.has(response.default_response_detail) ||
        !RESPONSE_DETAIL_SET.has(response.effective_response_detail) ||
        (response.selected_response_detail !== null &&
            !RESPONSE_DETAIL_SET.has(response.selected_response_detail))
    ) {
        return null;
    }
    const selected = response.selected_response_detail || null;
    const defaultDetail = response.default_response_detail;
    if (response.effective_response_detail !== (selected || defaultDetail)) {
        return null;
    }
    return {
        selected,
        defaultDetail,
        effective: response.effective_response_detail,
    };
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        panel.state.selectedResponseDetail = null;
        panel.state.defaultResponseDetail = "normal";
        panel.state.effectiveResponseDetail = "normal";
        panel.state.responseDetailLoading = false;
        panel.state.responseDetailSaving = false;

        const applyResponse = (response) => {
            const normalized = normalizeResponseDetailPreferences(response);
            if (!normalized) {
                return false;
            }
            panel.state.selectedResponseDetail = normalized.selected;
            panel.state.defaultResponseDetail = normalized.defaultDetail;
            panel.state.effectiveResponseDetail = normalized.effective;
            return true;
        };

        const loadResponseDetailPreferences = async () => {
            if (panel.state.responseDetailLoading) {
                return false;
            }
            panel.state.responseDetailLoading = true;
            try {
                return applyResponse(await rpc("/odoo_ai/v1/response-detail", {}));
            } catch {
                return false;
            } finally {
                panel.state.responseDetailLoading = false;
            }
        };

        const setResponseDetail = async (responseDetail) => {
            const normalized = responseDetail || null;
            if (
                panel.state.responseDetailSaving ||
                (normalized !== null && !RESPONSE_DETAIL_SET.has(normalized))
            ) {
                return false;
            }
            panel.state.responseDetailSaving = true;
            try {
                return applyResponse(
                    await rpc("/odoo_ai/v1/response-detail-set", {
                        response_detail: normalized,
                    })
                );
            } catch {
                return false;
            } finally {
                panel.state.responseDetailSaving = false;
            }
        };

        void loadResponseDetailPreferences();
        const baseOpen = panel.open.bind(panel);
        const baseToggle = panel.toggle.bind(panel);
        return {
            ...panel,
            open() {
                baseOpen();
                void loadResponseDetailPreferences();
            },
            toggle() {
                const wasOpen = panel.state.isOpen;
                baseToggle();
                if (!wasOpen && panel.state.isOpen) {
                    void loadResponseDetailPreferences();
                }
            },
            loadResponseDetailPreferences,
            setResponseDetail,
        };
    },
});
