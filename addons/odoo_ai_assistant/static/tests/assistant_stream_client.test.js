import { expect, test } from "@odoo/hoot";
import {
    readAssistantStream,
    streamAssistantChat,
} from "@odoo_ai_assistant/services/assistant_stream_client";

const encoder = new TextEncoder();

function responseFromStrings(strings, { contentType = "text/event-stream" } = {}) {
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
                    async cancel() {},
                    releaseLock() {},
                };
            },
        },
    };
}

function event(name, payload) {
    return `event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`;
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

test("browser streaming request keeps Odoo session CSRF and never needs assistant secret", async () => {
    const previousOdoo = globalThis.odoo;
    globalThis.odoo = { ...(previousOdoo || {}), csrf_token: "csrf-test-token" };
    let observedPath;
    let observedOptions;
    try {
        const result = await streamAssistantChat({
            payload: {
                message: "Lista presupuestos",
                screen: { model: "project.task" },
                conversation_id: null,
            },
            onDelta: () => {},
            fetchCall: async (path, options) => {
                observedPath = path;
                observedOptions = options;
                return responseFromStrings([
                    event("final", {
                        type: "final",
                        response: { ok: true, answer: "5 presupuestos" },
                    }),
                ]);
            },
        });

        expect(result.answer).toBe("5 presupuestos");
        expect(observedPath).toBe("/odoo_ai/v1/chat/stream");
        expect(observedOptions.credentials).toBe("same-origin");
        expect(observedOptions.headers.Accept).toBe("text/event-stream");
        expect(observedOptions.body.get("csrf_token")).toBe("csrf-test-token");
        expect(observedOptions.body.get("message")).toBe("Lista presupuestos");
        expect(observedOptions.body.get("screen")).toInclude("project.task");
        expect(JSON.stringify(observedOptions)).not.toInclude("Shared-Secret");
    } finally {
        globalThis.odoo = previousOdoo;
    }
});
