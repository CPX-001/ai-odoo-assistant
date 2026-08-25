/** @odoo-module **/

import { registry } from "@web/core/registry";

export const HISTORY_ACTION_REGISTRY = "odoo_ai_assistant.history_actions";
export const historyActionRegistry = registry.category(HISTORY_ACTION_REGISTRY);

historyActionRegistry.add(
    "select",
    {
        id: "select",
        label: "Seleccionar",
        icon: "fa-check-square-o",
        scopes: ["item"],
        run({ component, conversationIds }) {
            component.enterSelection(conversationIds[0]);
        },
    },
    { sequence: 10 }
);

historyActionRegistry.add(
    "delete",
    {
        id: "delete",
        label: "Eliminar",
        icon: "fa-trash",
        scopes: ["item", "bulk"],
        danger: true,
        async run({ component, conversationIds }) {
            await component.deleteConversations(conversationIds);
        },
    },
    { sequence: 90 }
);

export function historyActionsForScope(scope) {
    return historyActionRegistry
        .getAll()
        .filter((action) => Array.isArray(action.scopes) && action.scopes.includes(scope));
}
