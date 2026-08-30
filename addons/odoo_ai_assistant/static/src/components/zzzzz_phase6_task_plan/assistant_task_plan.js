/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import { selectVisibleTaskPlan } from "@odoo_ai_assistant/services/zzzzzz_phase6_task_plan_live_service";

patch(AssistantPanel.prototype, {
    get visibleTaskPlan() {
        return selectVisibleTaskPlan(this.state.liveTaskPlan, this.state.result?.task_plan);
    },
});
