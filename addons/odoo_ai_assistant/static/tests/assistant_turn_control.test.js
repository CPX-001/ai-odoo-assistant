import { expect, test } from "@odoo/hoot";
import { performedActionsState } from "@odoo_ai_assistant/components/assistant_panel/assistant_turn_control";
import {
    composerActionMode,
    normalizeRedirectResponse,
} from "@odoo_ai_assistant/services/zzzz_assistant_turn_control_service";

test("composer switches between stop redirect and send", () => {
    expect(
        composerActionMode({
            loading: true,
            draft: "",
            decisionLoading: false,
            recoveryPending: false,
            stopLoading: false,
        })
    ).toBe("stop");
    expect(
        composerActionMode({
            loading: true,
            draft: "  céntrate sólo en agosto  ",
            decisionLoading: false,
            recoveryPending: false,
            stopLoading: false,
        })
    ).toBe("redirect");
    expect(
        composerActionMode({
            loading: false,
            awaitingApproval: true,
            draft: "hazlo sólo para clientes",
            decisionLoading: false,
            recoveryPending: false,
            stopLoading: false,
        })
    ).toBe("redirect");
    expect(
        composerActionMode({
            loading: false,
            draft: "hola",
            decisionLoading: false,
            recoveryPending: false,
            stopLoading: false,
        })
    ).toBe("send");
});

test("redirect response stays bound to the current turn", () => {
    const turnId = "00000000-0000-4000-8000-000000000111";
    const response = {
        ok: true,
        turn_id: turnId,
        conversation_id: "00000000-0000-4000-8000-000000000222",
        state: "running",
        sequence: 2,
        resume_after_sequence: 7,
        message: {
            message_id: "00000000-0000-4000-8000-000000000333",
            role: "user",
            content: "ahora sólo agosto",
            created_at: "2026-08-29T12:00:00Z",
        },
    };
    expect(normalizeRedirectResponse(response, turnId)?.sequence).toBe(2);
    expect(normalizeRedirectResponse({ ...response, turn_id: "other-turn" }, turnId)).toBe(null);
    expect(normalizeRedirectResponse({ ...response, resume_after_sequence: -1 }, turnId)).toBe(null);
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
});
