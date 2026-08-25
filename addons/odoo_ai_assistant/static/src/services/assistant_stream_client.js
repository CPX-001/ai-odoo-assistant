/** @odoo-module **/

const MAX_STREAM_BYTES = 1024 * 1024;
const MAX_FRAME_CHARS = 128 * 1024;
const MAX_DELTA_CHARS = 4096;

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

export async function streamAssistantChat({ payload, onDelta, fetchCall = globalThis.fetch }) {
    if (typeof fetchCall !== "function") {
        throw new Error("stream_unavailable");
    }
    const csrfToken = globalThis.odoo?.csrf_token;
    if (typeof csrfToken !== "string" || !csrfToken) {
        throw new Error("csrf_unavailable");
    }
    let screen;
    try {
        screen = JSON.stringify(payload.screen);
    } catch {
        throw new Error("invalid_context");
    }
    if (!screen || screen.length > 16 * 1024) {
        throw new Error("invalid_context");
    }
    const body = new URLSearchParams();
    body.set("csrf_token", csrfToken);
    body.set("message", String(payload.message || ""));
    body.set("screen", screen);
    body.set("conversation_id", payload.conversation_id || "");

    const response = await fetchCall("/odoo_ai/v1/chat/stream", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            Accept: "text/event-stream",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
        body,
    });
    return readAssistantStream(response, onDelta);
}
