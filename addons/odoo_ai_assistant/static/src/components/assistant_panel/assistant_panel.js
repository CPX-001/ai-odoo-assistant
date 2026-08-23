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
        if (!context?.model) {
            return _t("No hay un modelo activo en esta pantalla.");
        }
        if (!context.res_id) {
            return context.model;
        }
        return `${context.model} #${context.res_id}`;
    }

    get errorMessage() {
        const messages = {
            access_denied: _t(
                "Odoo no permitió releer este registro con tus permisos actuales."
            ),
            action_budget_exceeded: _t("La acción superó los límites seguros del turno."),
            action_rejected: _t("La acción solicitada no está permitida."),
            approval_binding_mismatch: _t(
                "La propuesta pertenece a otro usuario, compañía o base de datos."
            ),
            approval_expired: _t(
                "La preview ha caducado. Genera una nueva antes de aprobar."
            ),
            approval_not_found: _t("No se encontró una aprobación ejecutable."),
            authentication_failed: _t(
                "La autenticación interna del Assistant Service ha fallado."
            ),
            engine_timeout: _t(
                "El motor de razonamiento agotó el tiempo disponible. Inténtalo de nuevo."
            ),
            engine_unavailable: _t("El motor de razonamiento no está disponible."),
            evidence_unavailable: _t(
                "No está disponible la evidencia de source necesaria para explicar este caso."
            ),
            invalid_context: _t(
                "Abre un registro guardado para poder explicar su contexto."
            ),
            invalid_response: _t("El Assistant Service devolvió una respuesta no válida."),
            invalid_workflow: _t("Elige uno de los flujos de lectura disponibles."),
            query_budget_exceeded: _t("La consulta superó los límites seguros del turno."),
            query_rejected: _t(
                "La consulta solicitada no está permitida por el esquema efectivo."
            ),
            proposal_already_decided: _t("Esta propuesta ya fue decidida."),
            proposal_not_found: _t("No se encontró la propuesta."),
            record_context_required: _t("Abre un registro guardado para usar ACTION."),
            service_unavailable: _t("El Assistant Service no está disponible."),
        };
        return messages[this.state.errorCode] || "";
    }

    get confidenceLabel() {
        const labels = {
            high: _t("Confianza alta"),
            medium: _t("Confianza media"),
            low: _t("Confianza baja"),
        };
        return labels[this.state.result?.confidence] || "";
    }

    get workflowDescription() {
        const descriptions = {
            EXPLAIN: _t("Explica el registro abierto con evidencia de runtime y source."),
            QUERY: _t(
                "Consulta el modelo actual mediante ORM acotado y permisos efectivos."
            ),
            HOW_TO: _t(
                "Construye una guía con menús, schema y documentación comprobados."
            ),
            ACTION: _t(
                "Prepara un cambio acotado; sólo se escribe tras tu aprobación explícita."
            ),
        };
        return descriptions[this.state.workflow] || "";
    }

    get questionPlaceholder() {
        const placeholders = {
            EXPLAIN: _t("¿Por qué ocurre esto en el registro abierto?"),
            QUERY: _t("¿Cuántos registros abiertos puedo ver?"),
            HOW_TO: _t("¿Cómo realizo esta tarea en esta instalación?"),
            ACTION: _t("Cambia el campo indicado al valor solicitado"),
        };
        return placeholders[this.state.workflow] || _t("Escribe una pregunta");
    }

    closePanel() {
        this.panel.close();
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

    get actionDecisionMessage() {
        const messages = {
            verified: _t("Cambio verificado mediante relectura de Odoo."),
            rejected: _t("Propuesta cancelada. No se realizó ningún cambio."),
            stale: _t("El registro cambió. Genera una nueva preview; no se forzó el cambio."),
            failed: _t("El cambio falló y no se presenta como completado."),
            execution_unknown: _t(
                "El resultado de ejecución es desconocido. No se reintentará automáticamente."
            ),
            committed_unverified: _t(
                "Odoo confirmó el commit, pero la relectura no pudo verificar el resultado."
            ),
        };
        return messages[this.state.actionReceipt?.state] || "";
    }

    get actionDecisionClass() {
        const actionState = this.state.actionReceipt?.state;
        if (actionState === "verified") {
            return "alert-success";
        }
        if (actionState === "rejected") {
            return "alert-secondary";
        }
        if (
            ["stale", "execution_unknown", "committed_unverified"].includes(
                actionState
            )
        ) {
            return "alert-warning";
        }
        return "alert-danger";
    }

    async approveAction() {
        await this.panel.decide("approve");
    }

    async rejectAction() {
        await this.panel.decide("reject");
    }

    async submit() {
        const question = this.form.question.trim();
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
