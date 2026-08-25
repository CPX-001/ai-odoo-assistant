import { expect, test } from "@odoo/hoot";
import {
    readAssistantStream,
    streamAssistantChat,
} from "@odoo_ai_assistant/services/assistant_stream_client";

const encoder = new TextEncoder();

function responseFromStrings(
    strings,
    { contentType = "text/event-stream", onCancel = () => {} } = {}
) {
    const chunks = strings.map((value) => encoder.encode(value));
    let index = 0;
    return {
        ok: true,
        headers: { get: () => contentType },
        body: {
            getReader() {
                return {
                    async read() {
                        if (index >= chunks.length) {
                            return { done: true, value: undefined };
                        }
                        const value = chunks[index];
                        index += 1;
                        return { done: false, value };
                    },
                    async cancel() {
                        onCancel();
                    },
                    releaseLock() {},
                };
            },
        },
    };
}

function event(name, payload) {
    return `event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function jsonResponse(result) {
    return {
        ok: true,
        async json() {
            return { jsonrpc: "2.0", id: 1, result };
        },
    };
}

test("browser stream accepts fragmented deltas and one terminal final", async () => {
    const deltas = [];
    const final = { ok: true, answer: "Hola mundo" };
    const first = event("delta", { type: "delta", text: "Hola " });
    const second = event("delta", { type: "delta", text: "mundo" });
    const terminal = event("final", { type: "final", response: final });
    const response = responseFromStrings([
        first.slice(0, 11),
        first.slice(11) + second + terminal.slice(0, 7),
        terminal.slice(7),
    ]);

    const result = await readAssistantStream(response, (text) => deltas.push(text));

    expect(deltas).toEqual(["Hola ", "mundo"]);
    expect(result).toEqual(final);
});

test("browser stream rejects unknown events and incomplete streams", async () => {
    let unknownFailed = false;
    try {
        await readAssistantStream(
            responseFromStrings([event("error", { type: "error" })])
        );
    } catch {
        unknownFailed = true;
    }
    expect(unknownFailed).toBe(true);

    let incompleteFailed = false;
    try {
        await readAssistantStream(
            responseFromStrings([event("delta", { type: "delta", text: "parcial" })])
        );
    } catch {
        incompleteFailed = true;
    }
    expect(incompleteFailed).toBe(true);
});

test("browser stream cancels its reader after the single authoritative final", async () => {
    let cancelCalls = 0;
    const response = responseFromStrings(
        [event("final", { type: "final", response: { ok: true } })],
        { onCancel: () => (cancelCalls += 1) }
    );

    expect(await readAssistantStream(response)).toEqual({ ok: true });
    expect(cancelCalls).toBe(1);
});

test("browser stream rejects a second final in the same received frame batch", async () => {
    const terminal = event("final", { type: "final", response: { ok: true } });
    let failed = false;

    try {
        await readAssistantStream(responseFromStrings([terminal + terminal]));
    } catch {
        failed = true;
    }

    expect(failed).toBe(true);
});

test("browser stream enforces delta, frame, and total-byte limits", async () => {
    const oversizedDelta = event("delta", { type: "delta", text: "x".repeat(4097) });
    const oversizedFrame = `event: delta\ndata: ${"x".repeat(128 * 1024)}\n\n`;
    const oversizedStream = "x".repeat(1024 * 1024 + 1);

    for (const payload of [oversizedDelta, oversizedFrame, oversizedStream]) {
        let failed = false;
        try {
            await readAssistantStream(responseFromStrings([payload]));
        } catch {
            failed = true;
        }
        expect(failed).toBe(true);
    }
});

test("product chat uses Odoo-native queue and status without assistant secret", async () => {
    const calls = [];
    const progress = [];
    const final = {
        ok: true,
        turn_id: "turn-1",
        conversation_id: "conversation-1",
        workflow: "AGENT",
        answer: "5 presupuestos",
        confidence: "high",
        limitations: [],
        citations: [],
        plan: {},
    };
    const result = await streamAssistantChat({
        payload: {
            message: "Lista presupuestos",
            screen: { model: "project.task" },
            conversation_id: null,
        },
        onDelta: (text) => progress.push(text),
        waitCall: async () => {},
        fetchCall: async (path, options) => {
            calls.push({ path, options });
            if (path === "/odoo_ai/v1/turn") {
                return jsonResponse({
                    ok: true,
                    turn_id: "turn-1",
                    state: "queued",
                    last_sequence: 1,
                    events: [{ type: "queued" }],
                });
            }
            return jsonResponse({
                ok: true,
                turn_id: "turn-1",
                state: "completed",
                last_sequence: 4,
                events: [
                    { type: "started" },
                    { type: "reasoning.started" },
                    { type: "reasoning.completed" },
                ],
                response: final,
            });
        },
    });

    expect(result.answer).toBe("5 presupuestos");
    expect(calls.map((item) => item.path)).toEqual([
        "/odoo_ai/v1/turn",
        "/odoo_ai/v1/turn/status",
    ]);
    expect(calls[0].options.credentials).toBe("same-origin");
    expect(calls[0].options.headers.Accept).toBe("application/json");
    expect(JSON.parse(calls[0].options.body).params.message).toBe("Lista presupuestos");
    expect(JSON.stringify(calls)).not.toInclude("Shared-Secret");
    expect(progress).toEqual([
        "Petición en cola…\n",
        "Procesando petición…\n",
        "Analizando petición…\n",
        "Preparando respuesta…\n",
    ]);
});
