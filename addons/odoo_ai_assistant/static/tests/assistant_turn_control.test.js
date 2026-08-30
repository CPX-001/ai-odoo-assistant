import { expect, test } from "@odoo/hoot";
import { performedActionsState } from "@odoo_ai_assistant/components/assistant_panel/assistant_turn_control";
import {
    composerActionMode,
    newClientInterventionId,
    normalizeRedirectResponse,
} from "@odoo_ai_assistant/services/zzzz_assistant_turn_control_service";

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
