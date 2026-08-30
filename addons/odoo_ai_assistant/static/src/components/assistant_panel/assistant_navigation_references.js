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
        return _t("Abrir en Odoo");
    }
    if (reference.kind === "odoo_setting") {
        return _t("Abrir %s", reference.label);
    }
    if (reference.kind === "odoo_menu") {
        return _t("Ir a %s", reference.label);
    }
    return _t("Abrir %s", reference.label);
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

    async openFinalReference(reference) {
        const opened = await openPublicReference(reference, { actionService: this.actionService });
        this.state.publicReferenceNotice = opened
            ? ""
            : _t("Este enlace ya no está disponible con tus permisos o contexto actuales.");
        return opened;
    },
});
