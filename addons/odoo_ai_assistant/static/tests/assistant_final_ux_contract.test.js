import { expect, test } from "@odoo/hoot";
import {
    finalAssistantMessageId,
    finalTurnPresentation,
    reconcileFinalAssistantMessage,
} from "@odoo_ai_assistant/services/assistant_final_ux_contract";

function scope() {
    return {
        turnId: "12345678-1234-5678-1234-567812345678",
        turnState: "running",
        loading: true,
        result: null,
        actionReceipt: null,
        errorCode: null,
        failure: null,
        streamingText: "",
        currentActivity: null,
        messages: [
            {
                message_id: "user-1",
                role: "user",
                content: "Pregunta",
                created_at: "2026-08-29T01:00:00.000Z",
            },
        ],
    };
}

test("authoritative final answer is reconciled exactly once", () => {
    const current = scope();
    const turnId = current.turnId;
    const messageId = finalAssistantMessageId(turnId);
    current.messages.push(
        {
            message_id: messageId,
            role: "assistant",
            content: "Respuesta provisional que no debe ganar",
            created_at: "2026-08-29T01:00:01.000Z",
        },
        {
            message_id: messageId,
            role: "assistant",
            content: "Respuesta final",
            created_at: "2026-08-29T01:00:02.000Z",
        }
    );

    const changed = reconcileFinalAssistantMessage(current, {
        turnId,
        answer: "Respuesta final autoritativa",
    });

    expect(changed).toBe(true);
    expect(current.messages.filter((message) => message.message_id === messageId)).toHaveLength(1);
    expect(current.messages.at(-1).content).toBe("Respuesta final autoritativa");
});

test("reconciling the same final answer is idempotent", () => {
    const current = scope();
    const turnId = current.turnId;
    reconcileFinalAssistantMessage(current, {
        turnId,
        answer: "Respuesta final",
        createdAt: "2026-08-29T01:00:02.000Z",
    });

    const changed = reconcileFinalAssistantMessage(current, {
        turnId,
        answer: "Respuesta final",
        createdAt: "2026-08-29T01:00:03.000Z",
    });

    expect(changed).toBe(false);
    expect(current.messages).toHaveLength(2);
    expect(current.messages[1].created_at).toBe("2026-08-29T01:00:02.000Z");
});

test("approved turn replaces its provisional and suffixed local messages", () => {
    const current = scope();
    const turnId = current.turnId;
    const messageId = finalAssistantMessageId(turnId);
    current.messages.push(
        {
            message_id: messageId,
            role: "assistant",
            content: "Propuesta pendiente de aprobación",
            created_at: "2026-08-29T01:00:01.000Z",
        },
        {
            message_id: `${messageId}-final`,
            role: "assistant",
            content: "Respuesta final duplicada",
            created_at: "2026-08-29T01:00:02.000Z",
        }
    );

    const changed = reconcileFinalAssistantMessage(current, {
        turnId,
        answer: "Respuesta final autoritativa",
    });

    expect(changed).toBe(true);
    expect(current.messages.filter((message) => message.role === "assistant")).toHaveLength(1);
    expect(current.messages.at(-1).message_id).toBe(messageId);
    expect(current.messages.at(-1).content).toBe("Respuesta final autoritativa");
});

test("real public activity suppresses only the fallback waiting status", () => {
    const current = scope();
    current.currentActivity = { sequence: 1, label: "Consultando Odoo" };

    const presentation = finalTurnPresentation(current);

    expect(presentation.state).toBe("running");
    expect(presentation.show_activity).toBe(true);
    expect(presentation.show_waiting_status).toBe(false);
    expect(presentation.show_streaming_answer).toBe(false);
});

test("activity and answer deltas are independent presentation channels", () => {
    const current = scope();
    current.currentActivity = { sequence: 2, label: "Leyendo registros" };
    current.streamingText = "Respuesta parcial";

    const presentation = finalTurnPresentation(current);

    expect(presentation.show_activity).toBe(true);
    expect(presentation.show_streaming_answer).toBe(true);
    expect(presentation.show_waiting_status).toBe(false);
});

test("approval failure and recovery remain explicit terminal product states", () => {
    const approval = scope();
    approval.loading = false;
    approval.turnState = "awaiting_confirmation";
    expect(finalTurnPresentation(approval).state).toBe("approval");
    expect(finalTurnPresentation(approval).show_approval).toBe(true);

    const failure = scope();
    failure.loading = false;
    failure.turnState = "failed";
    failure.errorCode = "engine_timeout";
    expect(finalTurnPresentation(failure).state).toBe("failure");
    expect(finalTurnPresentation(failure).show_failure).toBe(true);

    const recovery = scope();
    recovery.loading = false;
    recovery.turnState = "recovery_required";
    expect(finalTurnPresentation(recovery).state).toBe("recovery");
    expect(finalTurnPresentation(recovery).show_recovery).toBe(true);
});
