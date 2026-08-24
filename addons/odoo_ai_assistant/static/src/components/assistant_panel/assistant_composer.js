/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

const VIEW_LABELS = {
    form: "Formulario",
    list: "Lista",
    tree: "Lista",
    kanban: "Kanban",
    calendar: "Calendario",
    graph: "Gráfico",
    pivot: "Pivote",
    activity: "Actividad",
    cohort: "Cohorte",
    gantt: "Gantt",
    map: "Mapa",
};

export function formatScreenContext(context, translate = (value) => value) {
    if (!context?.model) {
        return translate("Contexto general de Odoo");
    }
    const record = Number.isSafeInteger(context.res_id) && context.res_id > 0
        ? `${context.model} #${context.res_id}`
        : context.model;
    const viewType = typeof context.view_type === "string"
        ? context.view_type.trim().toLowerCase()
        : "";
    if (!viewType) {
        return record;
    }
    const rawViewLabel = VIEW_LABELS[viewType] || viewType;
    return `${record} · ${translate(rawViewLabel)}`;
}

export function shouldSubmitComposerKey(event) {
    return Boolean(
        event &&
        event.key === "Enter" &&
        !event.shiftKey &&
        !event.isComposing
    );
}

patch(AssistantPanel.prototype, {
    get contextLabel() {
        return formatScreenContext(this.state.context, _t);
    },

    onComposerKeydown(event) {
        if (!shouldSubmitComposerKey(event)) {
            return;
        }
        event.preventDefault();
        void this.submit();
    },
});
