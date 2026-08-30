import { expect, test } from "@odoo/hoot";
import { patchTranslations } from "@web/../tests/web_test_helpers";
import {
    composerActionLabel,
    composerTextareaIsDisabled,
    performedActionsState,
    submitTurnControlMessage,
} from "@odoo_ai_assistant/components/assistant_panel/assistant_turn_control";
import {
    applyAcceptedStopState,
    composerActionMode,
    newClientInterventionId,
    normalizeCancellationStatus,
    normalizeRedirectResponse,
} from "@odoo_ai_assistant/services/zzzz_assistant_turn_control_service";

test("terminal Stop acknowledgement immediately releases the composer", () => {
    const scope = { loading: true, stopRequested: true, turnState: "running" };
    expect(applyAcceptedStopState(scope, "cancelled")).toBe(true);
    expect(scope).toEqual({ loading: false, stopRequested: false, turnState: "cancelled" });
    const pending = { loading: true, stopRequested: true, turnState: "running" };
    expect(applyAcceptedStopState(pending, "cancel_requested")).toBe(true);
    expect(pending.loading).toBe(true);
});

test("Stop status is accepted only for the same durable turn and cancellation lifecycle", () => {
    const turnId = "00000000-0000-4000-8000-000000000111";
    expect(
        normalizeCancellationStatus(
            { ok: true, turn_id: turnId, state: "cancel_requested" },
            turnId
        )?.state
    ).toBe("cancel_requested");
    expect(
        normalizeCancellationStatus({ ok: true, turn_id: turnId, state: "cancelled" }, turnId)
            ?.state
    ).toBe("cancelled");
    expect(
        normalizeCancellationStatus({ ok: true, turn_id: "other", state: "cancelled" }, turnId)
    ).toBe(null);
    expect(
        normalizeCancellationStatus({ ok: true, turn_id: turnId, state: "completed" }, turnId)
    ).toBe(null);
});

test("composer switches between disabled send stop and redirect", () => {
    const base = {
        decisionLoading: false,
        recoveryPending: false,
        stopLoading: false,
    };
    expect(composerActionMode({ ...base, loading: false, draft: "" })).toBe("disabled");
    expect(composerActionMode({ ...base, loading: false, draft: "hola" })).toBe("send");
    expect(composerActionMode({ ...base, loading: true, draft: "" })).toBe("stop");
    expect(
        composerActionMode({
            ...base,
            loading: true,
            draft: "  céntrate sólo en agosto  ",
        })
    ).toBe("redirect");
    expect(
        composerActionMode({
            ...base,
            loading: false,
            awaitingApproval: true,
            draft: "hazlo sólo para clientes",
        })
    ).toBe("redirect");
    expect(
        composerActionMode({ ...base, loading: true, draft: "corrección", stopLoading: true })
    ).toBe("disabled");
});

test("submitted text clears immediately so a running turn exposes Stop", async () => {
    let finish;
    const pendingResult = new Promise((resolve) => {
        finish = resolve;
    });
    const state = {
        draft: "hola",
        loading: false,
        decisionLoading: false,
        stopLoading: false,
        errorCode: null,
    };
    const component = {
        state,
        recoveryPending: false,
        panel: {
            setDraft(value) {
                state.draft = value;
            },
            async submit(message) {
                expect(message).toBe("hola");
                state.loading = true;
                return pendingResult;
            },
        },
    };

    const submitted = submitTurnControlMessage(component);
    expect(state.draft).toBe("");
    expect(
        composerActionMode({
            loading: state.loading,
            draft: state.draft,
            decisionLoading: false,
            recoveryPending: false,
            stopLoading: false,
        })
    ).toBe("stop");
    finish(true);
    expect(await submitted).toBe(true);
});

test("failed submission restores only the original untouched draft", async () => {
    const state = {
        draft: "mensaje original",
        decisionLoading: false,
        stopLoading: false,
        errorCode: null,
    };
    const component = {
        state,
        recoveryPending: false,
        panel: {
            setDraft(value) {
                state.draft = value;
            },
            async submit() {
                return false;
            },
        },
    };
    expect(await submitTurnControlMessage(component)).toBe(false);
    expect(state.draft).toBe("mensaje original");

    component.panel.submit = async () => {
        state.draft = "corrección nueva";
        return false;
    };
    expect(await submitTurnControlMessage(component)).toBe(false);
    expect(state.draft).toBe("corrección nueva");
});

test("textarea remains editable while processing and action labels are accessible", () => {
    patchTranslations({});
    expect(
        composerTextareaIsDisabled({
            decisionLoading: false,
            recoveryPending: false,
            stopLoading: false,
        })
    ).toBe(false);
    expect(
        composerTextareaIsDisabled({
            decisionLoading: true,
            recoveryPending: false,
            stopLoading: false,
        })
    ).toBe(true);
    expect(composerActionLabel("stop")).toBe("Detener respuesta");
    expect(composerActionLabel("redirect")).toBe("Corregir instrucción");
    expect(composerActionLabel("send")).toBe("Enviar mensaje");
});

test("client intervention ids are opaque bounded UI ids", () => {
    const first = newClientInterventionId();
    const second = newClientInterventionId();
    expect(first.startsWith("ui:")).toBe(true);
    expect(first.length).toBeLessThan(129);
    expect(second).not.toBe(first);
});

test("redirect response stays idempotently bound to current turn and client intervention", () => {
    const turnId = "00000000-0000-4000-8000-000000000111";
    const clientInterventionId = "ui:00000000-0000-4000-8000-000000000444";
    const response = {
        ok: true,
        turn_id: turnId,
        conversation_id: "00000000-0000-4000-8000-000000000222",
        state: "running",
        sequence: 2,
        client_intervention_id: clientInterventionId,
        duplicate: false,
        resume_after_sequence: 7,
        message: {
            message_id: "00000000-0000-4000-8000-000000000333",
            role: "user",
            content: "ahora sólo agosto",
            created_at: "2026-08-29T12:00:00Z",
        },
    };
    expect(normalizeRedirectResponse(response, turnId, clientInterventionId)?.sequence).toBe(2);
    expect(
        normalizeRedirectResponse({ ...response, duplicate: true }, turnId, clientInterventionId)
            ?.duplicate
    ).toBe(true);
    expect(
        normalizeRedirectResponse({ ...response, turn_id: "other-turn" }, turnId, clientInterventionId)
    ).toBe(null);
    expect(
        normalizeRedirectResponse(
            { ...response, client_intervention_id: "ui:other-intervention" },
            turnId,
            clientInterventionId
        )
    ).toBe(null);
    expect(
        normalizeRedirectResponse(
            { ...response, resume_after_sequence: -1 },
            turnId,
            clientInterventionId
        )
    ).toBe(null);
});

test("performed action card exposes revert only for host-declared available compensation", () => {
    const result = {
        plan: {
            state: "completed",
            metadata: { revertible: true, reversion_state: "available" },
            steps: [{ step_id: "turn:0", title: "Actualizar contacto" }],
        },
    };
    expect(performedActionsState(result)).toEqual({
        reverted: false,
        canRevert: true,
        unsupported: false,
        steps: result.plan.steps,
    });
    expect(
        performedActionsState({
            plan: {
                ...result.plan,
                metadata: { revertible: false, reversion_state: "completed" },
            },
        })?.reverted
    ).toBe(true);
    expect(
        performedActionsState({
            plan: {
                ...result.plan,
                metadata: { revertible: false, reversion_state: "unavailable" },
            },
        })?.unsupported
    ).toBe(true);
});
