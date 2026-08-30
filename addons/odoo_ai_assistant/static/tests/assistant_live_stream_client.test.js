import { expect, test } from "@odoo/hoot";
import {
    normalizeLivePage,
    streamAssistantChatLive,
} from "@odoo_ai_assistant/services/assistant_live_stream_client";

function jsonResponse(result) {
    return {
        ok: true,
        async json() {
            return { jsonrpc: "2.0", id: 1, result };
        },
    };
}

function activity(sequence = 1) {
    return {
        sequence,
        turn_id: "turn-live-0001",
        kind: "capability.started",
        phase: "capability",
        status: "running",
        label: "Query Odoo records",
        resource: { model: "res.partner", record_ids: [], display_names: [] },
        references: [],
        capability: "odoo.query_records",
        progress: null,
        diagnostic_code: null,
        occurred_at: "2026-08-28T10:00:00.000000Z",
        activity_id: "activity:v1:0123456789abcdef0123456789abcdef",
    };
}

test("public activity answer and readable reasoning stay on separate browser channels", async () => {
    const deltas = [];
    const activities = [];
    const summaries = [];
    let statusCalls = 0;
    let liveCalls = 0;
    const result = await streamAssistantChatLive({
        payload: { message: "Hola", screen: {}, conversation_id: null },
        waitCall: async () => {},
        onDelta: async (text) => deltas.push(text),
        onActivity: async (event) => activities.push(event.label),
        onReasoningSummary: async (item) => summaries.push(item.text),
        fetchCall: async (path) => {
            if (path === "/odoo_ai/v1/turn") {
                return jsonResponse({
                    ok: true,
                    turn_id: "turn-live-0001",
                    state: "queued",
                    last_sequence: 1,
                    events: [],
                });
            }
            if (path === "/odoo_ai/v1/turn/live") {
                liveCalls += 1;
                if (liveCalls === 1) {
                    return jsonResponse({
                        ok: true,
                        turn_id: "turn-live-0001",
                        items: [
                            { sequence: 1, channel: "activity", event: activity(1) },
                            {
                                sequence: 2,
                                channel: "reasoning",
                                turn_id: "turn-live-0001",
                                item_id: "reasoning-1",
                                summary_index: 0,
                                text: "Comprobaré primero los contactos. ",
                                occurred_at: "2026-08-28T10:00:00.050000Z",
                            },
                            {
                                sequence: 3,
                                channel: "answer",
                                turn_id: "turn-live-0001",
                                text: "Hola ",
                                occurred_at: "2026-08-28T10:00:00.100000Z",
                            },
                        ],
                        last_sequence: 3,
                        has_more: false,
                    });
                }
                return jsonResponse({
                    ok: true,
                    turn_id: "turn-live-0001",
                    items: [],
                    last_sequence: 3,
                    has_more: false,
                });
            }
            statusCalls += 1;
            return jsonResponse({
                ok: true,
                turn_id: "turn-live-0001",
                state: statusCalls === 1 ? "running" : "completed",
                last_sequence: 3,
                events: [],
                response: statusCalls === 1 ? null : { ok: true, answer: "Hola final" },
            });
        },
    });
    expect(deltas).toEqual(["Hola "]);
    expect(activities).toEqual(["Query Odoo records"]);
    expect(summaries).toEqual(["Comprobaré primero los contactos. "]);
    expect(result.answer).toBe("Hola final");
});

test("raw or malformed reasoning-shaped live payload fails closed", () => {
    const raw = normalizeLivePage(
        {
            ok: true,
            turn_id: "turn-live-0001",
            items: [
                {
                    sequence: 1,
                    channel: "reasoning",
                    turn_id: "turn-live-0001",
                    item_id: "reasoning-1",
                    summary_index: 0,
                    text: "safe summary",
                    raw_reasoning: "must never cross",
                    occurred_at: "2026-08-28T10:00:00.000000Z",
                },
            ],
            last_sequence: 1,
            has_more: false,
        },
        "turn-live-0001",
        0
    );
    expect(raw).toBe(null);
});

test("transient polling reconnect reuses live cursor without duplicating answer", async () => {
    const deltas = [];
    let liveCalls = 0;
    let statusCalls = 0;
    const result = await streamAssistantChatLive({
        payload: { message: "Hola", screen: {}, conversation_id: null },
        waitCall: async () => {},
        onDelta: async (text) => deltas.push(text),
        fetchCall: async (path) => {
            if (path === "/odoo_ai/v1/turn") {
                return jsonResponse({
                    ok: true,
                    turn_id: "turn-live-0001",
                    state: "queued",
                    last_sequence: 0,
                    events: [],
                });
            }
            if (path === "/odoo_ai/v1/turn/live") {
                liveCalls += 1;
                if (liveCalls === 1) {
                    throw new Error("temporary network failure");
                }
                if (liveCalls === 2) {
                    return jsonResponse({
                        ok: true,
                        turn_id: "turn-live-0001",
                        items: [
                            {
                                sequence: 1,
                                channel: "answer",
                                turn_id: "turn-live-0001",
                                text: "abc",
                                occurred_at: "2026-08-28T10:00:00.000000Z",
                            },
                        ],
                        last_sequence: 1,
                        has_more: false,
                    });
                }
                return jsonResponse({
                    ok: true,
                    turn_id: "turn-live-0001",
                    items: [],
                    last_sequence: 1,
                    has_more: false,
                });
            }
            statusCalls += 1;
            return jsonResponse({
                ok: true,
                turn_id: "turn-live-0001",
                state: "completed",
                last_sequence: 1,
                events: [],
                response: { ok: true, answer: "abc" },
            });
        },
    });
    expect(deltas).toEqual(["abc"]);
    expect(statusCalls).toBe(1);
    expect(result.answer).toBe("abc");
});
