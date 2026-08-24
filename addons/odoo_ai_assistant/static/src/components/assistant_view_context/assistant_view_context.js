/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

patch(AssistantPanel.prototype, {
    get currentViewId() {
        return this.env?.services?.odoo_ai_screen_context?.currentViewId?.() ?? null;
    },
});
