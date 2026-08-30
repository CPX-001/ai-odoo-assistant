/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AssistantPanel } from "@odoo_ai_assistant/components/assistant_panel/assistant_panel";
import { composerActionMode } from "@odoo_ai_assistant/services/zzzz_assistant_turn_control_service";

export function performedActionsState(result) {
    const plan = result?.plan;
    if (!plan || plan.state !== "completed" || !Array.isArray(plan.steps) || !plan.steps.length) {
        return null;
    }
    const reversion = plan.metadata?.reversion_state;
    return {
        reverted: reversion === "completed",
        canRevert: plan.metadata?.revertible === true && reversion === "available",
        unsupported: reversion === "unavailable",
        steps: plan.steps,
    };
}

export function composerTextareaIsDisabled({ decisionLoading, recoveryPending, stopLoading }) {
    return Boolean(decisionLoading || recoveryPending || stopLoading);
}

export function composerActionLabel(mode) {
    const labels = {
        stop: String(_t("Detener respuesta")),
        redirect: String(_t("Corregir instrucción")),
        send: String(_t("Enviar mensaje")),
        disabled: String(_t("Enviar mensaje")),
    };
    return labels[mode] || labels.disabled;
}

export async function submitTurnControlMessage(component) {
    const draft = component.state.draft;
    const question = draft.trim();
    if (
        !question ||
        component.state.decisionLoading ||
        component.recoveryPending ||
        component.state.stopLoading
    ) {
        return false;
    }

    // Clear immediately so a newly running turn exposes Stop instead of treating the submitted
    // text as a pending redirect. Restore only when submission fails and the user has not typed a
    // newer correction in the meantime.
    component.panel.setDraft("");
    let sent = false;
    try {
        sent = await component.panel.submit(question);
    } catch {
        if (!component.state.errorCode) {
            component.state.errorCode = "service_unavailable";
        }
    }
    if (!sent && !component.state.draft) {
        component.panel.setDraft(draft);
    }
    return sent;
}

patch(AssistantPanel.prototype, {
    get composerActionMode() {
        return composerActionMode({
            loading: this.state.loading,
            draft: this.state.draft,
            decisionLoading: this.state.decisionLoading,
            recoveryPending: this.recoveryPending,
            stopLoading: this.state.stopLoading,
            awaitingApproval: this.state.result?.plan?.state === "awaiting_confirmation",
        });
    },

    get composerActionDisabled() {
        return this.composerActionMode === "disabled";
    },

    get composerTextareaDisabled() {
        return composerTextareaIsDisabled({
            decisionLoading: this.state.decisionLoading,
            recoveryPending: this.recoveryPending,
            stopLoading: this.state.stopLoading,
        });
    },

    get composerActionLabel() {
        return composerActionLabel(this.composerActionMode);
    },

    get performedActions() {
        return performedActionsState(this.state.result);
    },

    get performedActionsVisible() {
        return Boolean(this.performedActions);
    },

    get interruptedAfterEffects() {
        return this.state.turnState === "cancelled" && this.performedActionsVisible;
    },

    async onComposerAction() {
        if (this.composerActionMode === "stop") {
            return this.panel.stop();
        }
        if (["send", "redirect"].includes(this.composerActionMode)) {
            return this.submit();
        }
        return false;
    },

    async submit() {
        return submitTurnControlMessage(this);
    },

    requestRevertPerformedActions() {
        if (!this.performedActions?.canRevert || this.state.reversionLoading) {
            return false;
        }
        this.state.reversionConfirmationOpen = true;
        return true;
    },

    cancelRevertPerformedActions() {
        this.state.reversionConfirmationOpen = false;
    },

    async confirmRevertPerformedActions() {
        if (!this.state.reversionConfirmationOpen) {
            return false;
        }
        const reverted = await this.panel.revertLastAction();
        if (reverted) {
            this.state.reversionConfirmationOpen = false;
        }
        return reverted;
    },
});
