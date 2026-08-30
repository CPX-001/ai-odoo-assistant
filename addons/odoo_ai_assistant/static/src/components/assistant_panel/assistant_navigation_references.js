/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import {
    normalizeHostNavigationReferences,
    openPublicReference,
} from "@odoo_ai_assistant/services/assistant_public_reference_service";

export function finalAnswerReferences(result) {
    return normalizeHostNavigationReferences(result?.references || [], 12) || [];
}

export function finalReferenceActionLabel(reference) {
    if (!reference?.label) {
        return String(_t("Abrir en Odoo"));
    }
    if (reference.kind === "odoo_menu") {
        return String(_t("Ir a %s", reference.label));
    }
    return String(_t("Abrir %s", reference.label));
}

export function referenceKey(reference) {
    if (!reference || typeof reference !== "object") {
        return "reference:invalid";
    }
    switch (reference.kind) {
        case "odoo_record":
            return `odoo_record:${reference.model || ""}:${reference.record_id || "unknown"}`;
        case "odoo_model":
            return `odoo_model:${reference.model || "unknown"}`;
        case "odoo_action":
            return `odoo_action:${reference.action_id || "unknown"}`;
        case "odoo_view":
            return `odoo_view:${reference.model || ""}:${reference.view_id || "unknown"}`;
        case "odoo_menu":
            return `odoo_menu:${reference.menu_id || "unknown"}`;
        case "odoo_setting":
            return `odoo_setting:${reference.action_id || ""}:${reference.setting_field || "unknown"}`;
        default:
            return `reference:${reference.model || ""}:unknown`;
    }
}

patch(AssistantPanel.prototype, {
    get finalNavigationReferences() {
        return finalAnswerReferences(this.state.result);
    },

    get finalNavigationReferencesVisible() {
        return this.finalNavigationReferences.length > 0;
    },

    finalReferenceLabel(reference) {
        return finalReferenceActionLabel(reference);
    },

    activityReferenceKey(reference) {
        return referenceKey(reference);
    },

    async openFinalReference(reference) {
        const opened = await openPublicReference(reference, { actionService: this.actionService });
        this.state.publicReferenceNotice = opened
            ? ""
            : _t("Este enlace ya no está disponible con tus permisos o contexto actuales.");
        return opened;
    },
});
