/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";
import { onMounted, useState } from "@odoo/owl";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

patch(AssistantPanel.prototype, {
    setup() {
        super.setup(...arguments);
        this.viewContext = useState({ technicalName: null });
        this._viewContextRequest = 0;

        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => {
            if (this.state.isOpen) {
                this.refreshViewTechnicalName();
            }
        });
        onMounted(() => this.refreshViewTechnicalName());
    },

    async refreshViewTechnicalName() {
        const requestId = ++this._viewContextRequest;
        const technicalName =
            (await this.env?.services?.odoo_ai_screen_context?.currentViewTechnicalName?.()) ??
            null;
        if (requestId === this._viewContextRequest) {
            this.viewContext.technicalName = technicalName;
        }
    },

    get currentViewTechnicalName() {
        return this.viewContext.technicalName;
    },
});
