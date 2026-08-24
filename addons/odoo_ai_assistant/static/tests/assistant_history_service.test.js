import { expect, test } from "@odoo/hoot";
import "@odoo_ai_assistant/services/assistant_history_service";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

const SCREEN_CONTEXT = {
    capture() {
        return {
            action_id: null,
            menu_id: null,
            view_type: null,
            model: null,
            res_id: null,
            selected_ids: [],
            allowed_context_subset: {},
            captured_at: "2026-08-24T13:00:00.000Z",
        };
    },
};

test("history is the initial view until the user explicitly starts a chat", () => {
    const panel = assistantPanelService.start({}, { odoo_ai_screen_context: SCREEN_CONTEXT });

    expect(panel.state.historyView).toBe(true);
    expect(panel.state.conversationId).toBe(null);

    panel.newConversation();
    expect(panel.state.historyView).toBe(false);
    expect(panel.state.conversationId).toBe(null);

    panel.showHistory();
    expect(panel.state.historyView).toBe(true);
});
