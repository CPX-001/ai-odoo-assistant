import { expect, test } from "@odoo/hoot";
import { reduceReasoningSummaryParts } from "@odoo_ai_assistant/services/assistant_reasoning_summary_service";

function event(sequence, text, overrides = {}) {
    return {
        sequence,
        turn_id: "turn-live-0001",
        item_id: "reasoning-1",
        summary_index: 0,
        text,
        ...overrides,
    };
}

test("readable summary deltas group by provider summary part", () => {
    let parts = reduceReasoningSummaryParts([], event(1, "Primero "));
    parts = reduceReasoningSummaryParts(parts, event(2, "consultaré Odoo."));

    expect(parts).toHaveLength(1);
    expect(parts[0].text).toBe("Primero consultaré Odoo.");
    expect(parts[0].sequences).toEqual([1, 2]);
});

test("replayed summary sequence is idempotent", () => {
    let parts = reduceReasoningSummaryParts([], event(1, "Uno"));
    parts = reduceReasoningSummaryParts(parts, event(1, "Uno"));

    expect(parts).toHaveLength(1);
    expect(parts[0].text).toBe("Uno");
});

test("summary parts stay bounded and malformed input is inert", () => {
    let parts = reduceReasoningSummaryParts([], event(1, "a".repeat(100)), { maximumChars: 128 });
    parts = reduceReasoningSummaryParts(parts, event(2, "b".repeat(100)), { maximumChars: 128 });

    expect(parts.map((part) => part.text).join("")).toHaveLength(128);
    expect(reduceReasoningSummaryParts(parts, { raw_reasoning: "secret" })).toBe(parts);
});

test("distinct summary indexes remain distinct readable parts", () => {
    let parts = reduceReasoningSummaryParts([], event(1, "Primera"));
    parts = reduceReasoningSummaryParts(parts, event(2, "Segunda", { summary_index: 1 }));

    expect(parts).toHaveLength(2);
    expect(parts[0].key).toBe("reasoning-1:0");
    expect(parts[1].key).toBe("reasoning-1:1");
});
