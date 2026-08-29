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

    get composerActionLabel() {
        const labels = {
            stop: _t("Detener procesamiento"),
            redirect: _t("Enviar corrección"),
            send: _t("Enviar mensaje"),
            disabled: _t("Enviar mensaje"),
        };
        return labels[this.composerActionMode];
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
        const draft = this.state.draft;
        const question = draft.trim();
        if (
            !question ||
            this.state.decisionLoading ||
            this.recoveryPending ||
            this.state.stopLoading
        ) {
            return false;
        }
        this.panel.setDraft("");
        let sent = false;
        try {
            sent = await this.panel.submit(question);
        } catch {
            if (!this.state.errorCode) {
                this.state.errorCode = "service_unavailable";
            }
        }
        if (!sent) {
            this.panel.setDraft(draft);
        }
        return sent;
    },

    async revertPerformedActions() {
        return this.panel.revertLastAction();
    },
});
