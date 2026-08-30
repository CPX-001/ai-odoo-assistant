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
        const question = this.state.draft.trim();
        if (
            !question ||
            this.state.decisionLoading ||
            this.recoveryPending ||
            this.state.stopLoading
        ) {
            return false;
        }
        let sent = false;
        try {
            // Keep the correction visible while Odoo durably accepts it.  The draft is cleared only
            // after a validated Odoo response, never merely because a network request was started.
            sent = await this.panel.submit(question);
        } catch {
            if (!this.state.errorCode) {
                this.state.errorCode = "service_unavailable";
            }
        }
        if (sent) {
            this.panel.setDraft("");
        }
        return sent;
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
