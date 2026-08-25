/** @odoo-module **/

const MAX_STREAM_BYTES = 1024 * 1024;
const MAX_FRAME_CHARS = 128 * 1024;
const MAX_DELTA_CHARS = 4096;
const MAX_POLL_ATTEMPTS = 360;
const POLL_DELAY_MS = 500;

function exactKeys(value, expected) {
    return (
        value !== null &&
        typeof value === "object" &&
        Object.keys(value).sort().join("|") === [...expected].sort().join("|")
    );
}

function nextFrame(buffer) {
    const lf = buffer.indexOf("\n\n");
    const crlf = buffer.indexOf("\r\n\r\n");
    let index = -1;
    let delimiterLength = 0;
    if (lf >= 0 && (crlf < 0 || lf < crlf)) {
        index = lf;
        delimiterLength = 2;
    } else if (crlf >= 0) {
        index = crlf;
        delimiterLength = 4;
    }
    if (index < 0) {
        return null;
    }
    return {
        frame: buffer.slice(0, index),
        rest: buffer.slice(index + delimiterLength),
    };
}

function parseFrame(frame) {
    if (!frame || frame.length > MAX_FRAME_CHARS) {
        throw new Error("invalid_stream");
    }
    const lines = frame.split(/\r?\n/);
    if (
        lines.length !== 2 ||
        !lines[0].startsWith("event: ") ||
        !lines[1].startsWith("data: ")
    ) {
        throw new Error("invalid_stream");
    }
    const event = lines[0].slice(7).trim();
    if (!["delta", "final"].includes(event)) {
        throw new Error("invalid_stream");
    }
    let payload;
    try {
        payload = JSON.parse(lines[1].slice(6));
    } catch {
        throw new Error("invalid_stream");
    }
    if (event === "delta") {
        if (
            !exactKeys(payload, ["text", "type"]) ||
            payload.type !== "delta" ||
            typeof payload.text !== "string" ||
            !payload.text.length ||
            payload.text.length > MAX_DELTA_CHARS
        ) {
            throw new Error("invalid_stream");
        }
        return { event, payload };
    }
    if (!exactKeys(payload, ["response", "type"]) || payload.type !== "final") {
        throw new Error("invalid_stream");
    }
    return { event, payload };
}

export async function readAssistantStream(response, onDelta = () => {}) {
    const contentType = response?.headers?.get?.("Content-Type") || "";
    if (
        !response?.ok ||
        !contentType.toLowerCase().startsWith("text/event-stream") ||
        !response.body?.getReader
    ) {
        throw new Error("invalid_stream");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let totalBytes = 0;
    let finalResponse = null;
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (value) {
                totalBytes += value.byteLength;
                if (totalBytes > MAX_STREAM_BYTES) {
                    throw new Error("invalid_stream");
                }
                buffer += decoder.decode(value, { stream: !done });
                if (buffer.length > MAX_FRAME_CHARS && nextFrame(buffer) === null) {
                    throw new Error("invalid_stream");
                }
            } else if (done) {
                buffer += decoder.decode();
            }

            let extracted;
            while ((extracted = nextFrame(buffer)) !== null) {
                buffer = extracted.rest;
                const parsed = parseFrame(extracted.frame);
                if (finalResponse !== null) {
                    throw new Error("invalid_stream");
                }
                if (parsed.event === "delta") {
                    await onDelta(parsed.payload.text);
                } else {
                    finalResponse = parsed.payload.response;
                }
            }

            if (finalResponse !== null) {
                try {
                    await reader.cancel();
                } catch {
                    // The final event is already terminal; cancellation is best effort.
                }
                return finalResponse;
            }
            if (done) {
                if (buffer.trim()) {
                    throw new Error("invalid_stream");
                }
                throw new Error("stream_ended_without_final");
            }
        }
    } finally {
        try {
            reader.releaseLock?.();
        } catch {
            // Ignore cleanup differences between browser stream implementations.
        }
    }
}

async function jsonRoute(fetchCall, route, params) {
    const response = await fetchCall(route, {
        method: "POST",
        credentials: "same-origin",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params,
            id: Date.now(),
        }),
    });
    if (!response?.ok || typeof response.json !== "function") {
        throw new Error("runtime_unavailable");
    }
    const envelope = await response.json();
    if (envelope?.error || !Object.prototype.hasOwnProperty.call(envelope || {}, "result")) {
        throw new Error("runtime_unavailable");
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

async function emitProgress(events, onDelta, emitted) {
    if (!Array.isArray(events)) {
        return;
    }
    const labels = {
        queued: "Petición en cola…\n",
        started: "Procesando petición…\n",
        "reasoning.started": "Analizando petición…\n",
        "tool.started": "Consultando datos…\n",
        "reasoning.completed": "Preparando respuesta…\n",
    };
    for (const event of events) {
        const text = labels[event?.type];
        if (text && !emitted.has(text)) {
            emitted.add(text);
            await onDelta(text);
        }
    }
}

export async function streamAssistantChat({
    payload,
    onDelta = () => {},
    fetchCall = globalThis.fetch,
    waitCall = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
}) {
    if (typeof fetchCall !== "function") {
        throw new Error("stream_unavailable");
    }
    if (
        typeof payload?.message !== "string" ||
        !payload.message.trim() ||
        payload.message.length > 4000 ||
        payload.screen === null ||
        typeof payload.screen !== "object"
    ) {
        throw new Error("invalid_context");
    }
    const emitted = new Set();
    const queued = await jsonRoute(fetchCall, "/odoo_ai/v1/turn", {
        message: payload.message,
        screen: payload.screen,
        conversation_id: payload.conversation_id || null,
        client_request_id: requestId(),
    });
    if (queued?.ok !== true || typeof queued.turn_id !== "string") {
        throw new Error(queued?.error?.code || "runtime_unavailable");
    }
    await emitProgress(queued.events, onDelta, emitted);
    let afterSequence = Number.isSafeInteger(queued.last_sequence) ? queued.last_sequence : 0;
    if (queued.state === "completed" && queued.response) {
        return queued.response;
    }

    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
        await waitCall(POLL_DELAY_MS);
        const status = await jsonRoute(fetchCall, "/odoo_ai/v1/turn/status", {
            turn_id: queued.turn_id,
            after_sequence: afterSequence,
        });
        if (status?.ok !== true || status.turn_id !== queued.turn_id) {
            throw new Error(status?.error?.code || "runtime_unavailable");
        }
        await emitProgress(status.events, onDelta, emitted);
        if (Number.isSafeInteger(status.last_sequence)) {
            afterSequence = status.last_sequence;
        }
        if (status.state === "completed") {
            if (status.response?.ok !== true) {
                throw new Error("invalid_response");
            }
            return status.response;
        }
        if (["failed", "cancelled", "recovery_required"].includes(status.state)) {
            throw new Error(status.error_code || "runtime_unavailable");
        }
    }
    throw new Error("engine_timeout");
}
