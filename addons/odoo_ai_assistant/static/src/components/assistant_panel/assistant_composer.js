/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";

export function formatScreenContext(context, translate = (value) => value) {
    if (!context?.model) {
        return translate("Contexto general de Odoo");
    }
    return Number.isSafeInteger(context.res_id) && context.res_id > 0
        ? `${context.model} #${context.res_id}`
        : context.model;
}

export function shouldSubmitComposerKey(event) {
    return Boolean(
        event &&
        event.key === "Enter" &&
        !event.shiftKey &&
        !event.isComposing
    );
}

export async function submitComposerMessage(component) {
    const draft = component.state.draft;
    const question = draft.trim();
    if (
        !question ||
        component.state.loading ||
        component.state.decisionLoading ||
        component.recoveryPending
    ) {
        return false;
    }

    // The panel service owns optimistic chat messages. Keeping that state transition
    // in one layer avoids rendering the same user message twice while streaming.
    component.panel.setDraft("");

    let sent = false;
    try {
        sent = await component.panel.submit(question);
    } catch {
        if (!component.state.errorCode) {
            component.state.errorCode = "service_unavailable";
        }
    }

    if (!sent) {
        component.panel.setDraft(draft);
    }
    return sent;
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

    async submit() {
        return submitComposerMessage(this);
    },
});
