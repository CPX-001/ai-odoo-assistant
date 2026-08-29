/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

function activeScope(state) {
    return state.turnScopes?.[state.activeTurnScopeKey] || null;
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const service = super.start(env, dependencies);
        const state = service.state;
        const baseSubmit = service.submit.bind(service);

        service.submit = async (message) => {
            const scope = activeScope(state);
            const result = await baseSubmit(message);
            if (result && scope?.stopRequested) {
                scope.stopRequested = false;
            }
            return result;
        };
        return service;
    },
});
