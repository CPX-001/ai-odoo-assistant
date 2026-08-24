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
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => {
            if (this.state.isOpen) {
                this.panel.refreshContext();
            }
        });
    }

    get contextLabel() {
        const context = this.state.context;
        if (!context?.model) {
            return _t("Contexto general de Odoo");
        }
        if (!context.res_id) {
            return context.model;
        }
        return `${context.model} #${context.res_id}`;
    }

    get errorMessage() {
        const messages = {
            access_denied: _t("No tienes permisos para acceder a los datos necesarios."),
            action_budget_exceeded: _t("La acción superó los límites seguros del turno."),
            action_rejected: _t("La acción solicitada no está permitida."),
            approval_binding_mismatch: _t("La propuesta pertenece a otro contexto de usuario."),
            approval_expired: _t("La preview ha caducado. Pide de nuevo el cambio."),
            approval_not_found: _t("No se encontró una aprobación ejecutable."),
            authentication_failed: _t("La autenticación interna del Assistant ha fallado."),
            chat_store_unavailable: _t("El historial no está disponible temporalmente."),
            engine_timeout: _t("Codex agotó el tiempo disponible. Inténtalo de nuevo."),
            engine_unavailable: _t("Codex no está disponible en este momento."),
            evidence_unavailable: _t("No está disponible la evidencia necesaria."),
            invalid_context: _t("No se pudo interpretar la petición o el contexto actual."),
            invalid_response: _t("El Assistant devolvió una respuesta no válida."),
            query_budget_exceeded: _t("La consulta superó los límites seguros del turno."),
            query_rejected: _t("La consulta no está permitida por el esquema efectivo."),
            proposal_already_decided: _t("Esta propuesta ya fue decidida."),
            proposal_not_found: _t("No se encontró la propuesta."),
            record_context_required: _t("Esta acción necesita un registro abierto."),
            service_unavailable: _t("El Assistant Service no está disponible."),
        };
        return messages[this.state.errorCode] || _t("No se pudo completar la petición.");
    }

    get confidenceLabel() {
        const labels = {
            high: _t("Confianza alta"),
            medium: _t("Confianza media"),
            low: _t("Confianza baja"),
        };
        return labels[this.state.result?.confidence] || "";
    }

    get actionDecisionMessage() {
        const messages = {
            verified: _t("Cambio verificado mediante relectura de Odoo."),
            rejected: _t("Propuesta cancelada. No se realizó ningún cambio."),
            stale: _t("El registro cambió. Pide una nueva preview."),
            failed: _t("El cambio falló y no se presenta como completado."),
            execution_unknown: _t("El resultado es desconocido y no se reintentará solo."),
            committed_unverified: _t("El commit se realizó, pero no pudo verificarse."),
        };
        return messages[this.state.actionReceipt?.state] || "";
    }

    get actionDecisionClass() {
        const value = this.state.actionReceipt?.state;
        if (value === "verified") {
            return "alert-success";
        }
        if (value === "rejected") {
            return "alert-secondary";
        }
        if (["stale", "execution_unknown", "committed_unverified"].includes(value)) {
            return "alert-warning";
        }
        return "alert-danger";
    }

    closePanel() {
        this.panel.close();
    }

    newConversation() {
        this.panel.newConversation();
    }

    async selectConversation(event) {
        const value = event.target.value;
        if (value) {
            await this.panel.selectConversation(value);
        } else {
            this.panel.newConversation();
        }
    }

    onDraftInput(event) {
        this.panel.setDraft(event.target.value);
    }

    formatActionValue(value) {
        if (!value || value.value === null) {
            return _t("Vacío");
        }
        if (value.kind === "boolean") {
            return value.value ? _t("Sí") : _t("No");
        }
        if (value.kind === "many2one") {
            return `#${value.value}`;
        }
        return String(value.value);
    }

    async approveAction() {
        await this.panel.decide("approve");
    }

    async rejectAction() {
        await this.panel.decide("reject");
    }

    async submit() {
        const question = this.state.draft.trim();
        if (!question || this.state.loading || this.state.decisionLoading) {
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
