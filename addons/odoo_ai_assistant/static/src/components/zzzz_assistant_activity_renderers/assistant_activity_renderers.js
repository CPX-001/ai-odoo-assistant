/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import { renderActivityLabel } from "@odoo_ai_assistant/services/assistant_activity_renderer_registry";

function technicalSuffix(item, preferences) {
    if (
        (!preferences?.show_technical_names && preferences?.detail_level !== "diagnostic") ||
        !item
    ) {
        return "";
    }
    const technical = [];
    if (item.capability) {
        technical.push(item.capability);
    }
    if (item.resource?.model && !technical.includes(item.resource.model)) {
        technical.push(item.resource.model);
    }
    if (!technical.length && item.label) {
        technical.push(item.label);
    }
    return technical.length ? ` · ${technical.join(" · ")}` : "";
}

/**
 * One stable patch connects the existing AssistantPanel to an Odoo registry. Addons extending
 * the Assistant should register renderers instead of adding more panel patches.
 */
patch(AssistantPanel.prototype, {
    get activityItems() {
        const items = super.activityItems;
        const preferences = this.semanticActivity?.preferences;
        return items.map((item) => {
            const rendered = renderActivityLabel(item);
            if (!rendered) {
                return item;
            }
            return {
                ...item,
                display_label: `${rendered}${technicalSuffix(item, preferences)}`,
            };
        });
    },
});
