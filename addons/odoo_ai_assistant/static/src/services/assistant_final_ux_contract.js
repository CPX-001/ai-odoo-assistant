/** @odoo-module **/

const LOCAL_ASSISTANT_MESSAGE_PREFIX = "local-assistant-";

function safeMessages(scope) {
    return Array.isArray(scope?.messages) ? scope.messages : [];
}

function hasRecovery(scope) {
    return Boolean(
        scope?.actionReceipt?.state === "recovery_required" ||
        scope?.turnState === "recovery_required"
    );
}

function hasExecution(scope) {
    if (hasRecovery(scope)) {
        return false;
    }
    if (["completed", "failed", "cancelled"].includes(scope?.turnState)) {
        return false;
    }
    if (["completed", "partial", "failed", "rejected"].includes(scope?.actionReceipt?.state)) {
        return false;
    }
    return ["authorized", "executing"].includes(scope?.result?.plan?.state);
}

function hasApproval(scope) {
    return (
        scope?.result?.plan?.state === "awaiting_confirmation" ||
        scope?.turnState === "awaiting_confirmation"
    );
}

function hasFailure(scope) {
    return Boolean(scope?.failure || scope?.errorCode || scope?.turnState === "failed");
}

export function finalAssistantMessageId(turnId) {
    if (typeof turnId !== "string" || !turnId) {
        throw new Error("invalid_turn_id");
    }
    return `${LOCAL_ASSISTANT_MESSAGE_PREFIX}${turnId}`;
}

/**
 * Reconcile the authoritative final answer into exactly one local Assistant message.
 *
 * Provisional answer deltas never enter the durable/local message list. This helper is
 * deliberately idempotent so repeated final projection/reopen callbacks cannot duplicate
 * the authoritative answer for one turn.
 */
export function reconcileFinalAssistantMessage(
    scope,
    { turnId, answer, createdAt = null } = {}
) {
    if (!scope || typeof scope !== "object") {
        throw new Error("invalid_turn_scope");
    }
    if (typeof answer !== "string" || !answer) {
        return false;
    }
    const messageId = finalAssistantMessageId(turnId);
    const messages = safeMessages(scope);
    const isTurnLocalMessage = (message) =>
        message?.message_id === messageId || message?.message_id?.startsWith(`${messageId}-`);
    const matching = messages.filter(isTurnLocalMessage);
    const previous = matching.length ? matching[matching.length - 1] : null;
    const canonical = {
        ...(previous || {}),
        message_id: messageId,
        role: "assistant",
        content: answer,
        created_at:
            previous?.created_at ||
            (typeof createdAt === "string" && createdAt ? createdAt : new Date().toISOString()),
    };

    let inserted = false;
    const next = [];
    for (const message of messages) {
        if (!isTurnLocalMessage(message)) {
            next.push(message);
            continue;
        }
        if (message === previous && !inserted) {
            next.push(canonical);
            inserted = true;
        }
    }
    if (!inserted) {
        next.push(canonical);
    }

    const changed =
        matching.length !== 1 ||
        matching[0]?.role !== "assistant" ||
        matching[0]?.content !== answer;
    if (changed) {
        scope.messages = next;
    }
    return changed;
}

/**
 * Closed product-facing presentation projection. Activity and answer streaming are separate
 * booleans because they may legitimately be visible at the same time.
 */
export function finalTurnPresentation(scope) {
    const loading = Boolean(scope?.loading);
    const streamingAnswer = loading && Boolean(scope?.streamingText);
    const activity = Boolean(scope?.currentActivity);
    const recovery = hasRecovery(scope);
    const execution = hasExecution(scope);
    const approval = !recovery && !execution && hasApproval(scope);
    const failure = !recovery && !execution && !approval && hasFailure(scope);

    let state = "idle";
    if (recovery) {
        state = "recovery";
    } else if (approval) {
        state = "approval";
    } else if (failure) {
        state = "failure";
    } else if (loading || execution) {
        state = "running";
    } else if (scope?.result || scope?.turnState === "completed") {
        state = "completed";
    }

    return Object.freeze({
        state,
        show_activity: activity,
        show_streaming_answer: streamingAnswer,
        show_waiting_status: loading && !activity && !streamingAnswer,
        show_failure: failure,
        show_approval: approval,
        show_recovery: recovery,
    });
}
