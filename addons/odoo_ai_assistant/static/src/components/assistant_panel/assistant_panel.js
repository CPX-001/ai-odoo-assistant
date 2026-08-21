/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";

export class AssistantSystray extends Component {
    static template = "odoo_ai_assistant.AssistantSystray";
    static props = {};

    setup() {
        this.panel = useService("odoo_ai_assistant_panel");
        this.state = useState(this.panel.state);
    }

    togglePanel() {
        this.panel.toggle();
    }
}

export class AssistantPanel extends Component {
    static template = "odoo_ai_assistant.AssistantPanel";
    static props = {};

    setup() {
        this.panel = useService("odoo_ai_assistant_panel");
        this.state = useState(this.panel.state);
        this.form = useState({ question: "" });
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => {
            if (this.state.isOpen) {
                this.panel.refreshContext();
            }
        });
    }

    get contextLabel() {
        const context = this.state.context;
        if (!context?.model || !context?.res_id) {
            return _t("No hay un registro abierto en esta pantalla.");
        }
        return `${context.model} #${context.res_id}`;
    }

    get errorMessage() {
        const messages = {
            access_denied: _t(
                "Odoo no permitió releer este registro con tus permisos actuales."
            ),
            authentication_failed: _t(
                "La autenticación interna del Assistant Service ha fallado."
            ),
            invalid_context: _t(
                "Abre un registro guardado para comprobar su contexto en M2."
            ),
            invalid_response: _t("El Assistant Service devolvió una respuesta no válida."),
            service_unavailable: _t("El Assistant Service no está disponible."),
        };
        return messages[this.state.errorCode] || "";
    }

    get resultFields() {
        return Object.entries(this.state.result?.fields || {});
    }

    closePanel() {
        this.panel.close();
    }

    async submit() {
        const question = this.form.question.trim();
        if (!question || this.state.loading) {
            return;
        }
        await this.panel.submit(question);
    }
}

registry.category("systray").add(
    "odoo_ai_assistant.systray",
    { Component: AssistantSystray },
    { sequence: 35 }
);
registry.category("main_components").add("odoo_ai_assistant.panel", {
    Component: AssistantPanel,
});
