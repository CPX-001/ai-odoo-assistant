/** @odoo-module **/

import {
    AssistantFailureError,
    boundedFailureCode,
    failureErrorFromStatus,
} from "@odoo_ai_assistant/services/assistant_failure_contract";
import { normalizePublicTurnEvent } from "@odoo_ai_assistant/services/assistant_public_activity_contract";

const MAX_POLL_ATTEMPTS = 360;
const POLL_DELAY_MS = 500;
const MAX_LIVE_ITEMS = 100;
const MAX_DELTA_CHARS = 2048;
const MAX_TRANSIENT_POLL_FAILURES = 3;

function exactKeys(value, expected) {
    return (
        value !== null &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        Object.keys(value).sort().join("|") === [...expected].sort().join("|")
    );
}

async function jsonRoute(fetchCall, route, params) {
    let response;
    try {
        response = await fetchCall(route, {
            method: "POST",
            credentials: "same-origin",
            headers: { Accept: "application/json", "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params, id: Date.now() }),
        });
    } catch {
        throw new AssistantFailureError("runtime_unavailable");
    }
    if (!response?.ok || typeof response.json !== "function") {
        throw new AssistantFailureError("runtime_unavailable");
    }
    const envelope = await response.json();
    if (envelope?.error || !Object.prototype.hasOwnProperty.call(envelope || {}, "result")) {
        throw new AssistantFailureError("runtime_unavailable");
    }
    return envelope.result;
}

function requestId() {
    const uuid = globalThis.crypto?.randomUUID?.();
    if (typeof uuid === "string" && uuid.length >= 8) {
        return uuid;
    }
    return `web-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

function defaultNow() {
    const value = globalThis.performance?.now?.();
    return Number.isFinite(value) ? value : Date.now();
}

async function emitTiming(onTiming, nowCall, startedAt, point, detail = {}) {
    const elapsed = Math.max(0, Number(nowCall()) - startedAt);
    await onTiming({ point, elapsed_ms: Math.round(elapsed * 1000) / 1000, ...detail });
}

function terminalResponse(status) {
    if (["completed", "awaiting_confirmation"].includes(status?.state)) {
        if (status.response?.ok !== true) {
            throw new AssistantFailureError("invalid_response");
        }
        return status.response;
    }
    return null;
}

function normalizeLiveItem(value, turnId, previousSequence) {
    if (!value || !Number.isSafeInteger(value.sequence) || value.sequence <= previousSequence) {
        return null;
    }
    if (value.channel === "activity" && exactKeys(value, ["channel", "event", "sequence"])) {
        const event = normalizePublicTurnEvent(value.event);
        if (!event || event.turn_id !== turnId || event.sequence !== value.sequence) {
            return null;
        }
        return { sequence: value.sequence, channel: "activity", event };
    }
    if (
        value.channel === "answer" &&
        exactKeys(value, ["channel", "occurred_at", "sequence", "text", "turn_id"]) &&
        value.turn_id === turnId &&
        typeof value.text === "string" &&
        value.text.length >= 1 &&
        value.text.length <= MAX_DELTA_CHARS &&
        !value.text.includes("\u0000") &&
        typeof value.occurred_at === "string"
    ) {
        return {
            sequence: value.sequence,
            channel: "answer",
            text: value.text,
            occurred_at: value.occurred_at,
        };
    }
    return null;
}

function normalizeLivePage(value, turnId, afterSequence) {
    if (
        !exactKeys(value, ["has_more", "items", "last_sequence", "ok", "turn_id"]) ||
        value.ok !== true ||
        value.turn_id !== turnId ||
        !Array.isArray(value.items) ||
        value.items.length > MAX_LIVE_ITEMS ||
        typeof value.has_more !== "boolean" ||
        !Number.isSafeInteger(value.last_sequence) ||
        value.last_sequence < afterSequence
    ) {
        return null;
    }
    const items = [];
    let previous = afterSequence;
    for (const raw of value.items) {
        const item = normalizeLiveItem(raw, turnId, previous);
        if (!item) {
            return null;
        }
        items.push(item);
        previous = item.sequence;
    }
    if (items.length && value.last_sequence !== items[items.length - 1].sequence) {
        return null;
    }
    if (!items.length && value.last_sequence !== afterSequence) {
        return null;
    }
    return { ...value, items };
}

async function drainLive({
    fetchCall,
    turnId,
    afterSequence,
    onActivity,
    onDelta,
    onFirstActivity,
    onFirstAnswerDelta,
}) {
    let cursor = afterSequence;
    for (let pageIndex = 0; pageIndex < 16; pageIndex += 1) {
        const raw = await jsonRoute(fetchCall, "/odoo_ai/v1/turn/live", {
            turn_id: turnId,
            after_sequence: cursor,
        });
        const page = normalizeLivePage(raw, turnId, cursor);
        if (!page) {
            throw new AssistantFailureError("invalid_response");
        }
        for (const item of page.items) {
            cursor = item.sequence;
            if (item.channel === "activity") {
                await onActivity(item.event);
                await onFirstActivity();
            } else {
                await onDelta(item.text);
                await onFirstAnswerDelta();
            }
        }
        if (!page.has_more) {
            return cursor;
        }
    }
    throw new AssistantFailureError("invalid_response");
}

export async function streamAssistantChatLive({
    payload,
    onDelta = () => {},
    onActivity = () => {},
    onTiming = () => {},
    fetchCall = globalThis.fetch,
    waitCall = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
    nowCall = defaultNow,
}) {
    if (
        typeof fetchCall !== "function" ||
        typeof onDelta !== "function" ||
        typeof onActivity !== "function" ||
        typeof onTiming !== "function" ||
        typeof nowCall !== "function"
    ) {
        throw new AssistantFailureError("invalid_context");
    }
    if (
        typeof payload?.message !== "string" ||
        !payload.message.trim() ||
        payload.message.length > 4000 ||
        payload.screen === null ||
        typeof payload.screen !== "object"
    ) {
        throw new AssistantFailureError("invalid_context");
    }

    const startedAt = Number(nowCall());
    if (!Number.isFinite(startedAt)) {
        throw new AssistantFailureError("invalid_context");
    }
    await onTiming({ point: "submit_received", elapsed_ms: 0 });
    const queued = await jsonRoute(fetchCall, "/odoo_ai/v1/turn", {
        message: payload.message,
        screen: payload.screen,
        conversation_id: payload.conversation_id || null,
        client_request_id: requestId(),
    });
    if (queued?.ok !== true || typeof queued.turn_id !== "string") {
        throw new AssistantFailureError(
            boundedFailureCode(queued?.error?.code || queued?.error_code, "runtime_unavailable")
        );
    }
    const turnId = queued.turn_id;
    await emitTiming(onTiming, nowCall, startedAt, "turn_persisted", { turn_id: turnId });

    let liveSequence = 0;
    let statusSequence = Number.isSafeInteger(queued.last_sequence) ? queued.last_sequence : 0;
    let firstActivity = false;
    let firstAnswerDelta = false;
    let transientFailures = 0;
    const recordFirstActivity = async () => {
        if (!firstActivity) {
            firstActivity = true;
            await emitTiming(onTiming, nowCall, startedAt, "browser_first_activity", { turn_id: turnId });
        }
    };
    const recordFirstAnswerDelta = async () => {
        if (!firstAnswerDelta) {
            firstAnswerDelta = true;
            await emitTiming(onTiming, nowCall, startedAt, "browser_first_answer_delta", { turn_id: turnId });
        }
    };

    const immediate = terminalResponse(queued);
    if (immediate) {
        await emitTiming(onTiming, nowCall, startedAt, "browser_final", {
            turn_id: turnId,
            state: queued.state,
        });
        return immediate;
    }
    if (["failed", "cancelled", "recovery_required"].includes(queued.state)) {
        throw failureErrorFromStatus(queued);
    }

    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
        await waitCall(POLL_DELAY_MS);
        try {
            liveSequence = await drainLive({
                fetchCall,
                turnId,
                afterSequence: liveSequence,
                onActivity,
                onDelta,
                onFirstActivity: recordFirstActivity,
                onFirstAnswerDelta: recordFirstAnswerDelta,
            });
            const status = await jsonRoute(fetchCall, "/odoo_ai/v1/turn/status", {
                turn_id: turnId,
                after_sequence: statusSequence,
            });
            if (status?.ok !== true || status.turn_id !== turnId) {
                throw new AssistantFailureError(
                    boundedFailureCode(status?.error?.code || status?.error_code, "runtime_unavailable")
                );
            }
            transientFailures = 0;
            if (Number.isSafeInteger(status.last_sequence)) {
                statusSequence = status.last_sequence;
            }
            const response = terminalResponse(status);
            if (response) {
                liveSequence = await drainLive({
                    fetchCall,
                    turnId,
                    afterSequence: liveSequence,
                    onActivity,
                    onDelta,
                    onFirstActivity: recordFirstActivity,
                    onFirstAnswerDelta: recordFirstAnswerDelta,
                });
                await emitTiming(onTiming, nowCall, startedAt, "browser_final", {
                    turn_id: turnId,
                    state: status.state,
                });
                return response;
            }
            if (["failed", "cancelled", "recovery_required"].includes(status.state)) {
                throw failureErrorFromStatus(status);
            }
        } catch (error) {
            if (
                error instanceof AssistantFailureError &&
                error.message === "runtime_unavailable" &&
                transientFailures < MAX_TRANSIENT_POLL_FAILURES
            ) {
                transientFailures += 1;
                continue;
            }
            throw error;
        }
    }
    throw new AssistantFailureError("engine_timeout");
}

export { normalizeLivePage };
