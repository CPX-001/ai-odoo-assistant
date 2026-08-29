import { expect, test } from "@odoo/hoot";
import {
    reduceSemanticActivity,
    semanticActivityPresentation,
} from "@odoo_ai_assistant/services/assistant_semantic_activity";

const FIRST = "activity:v1:11111111111111111111111111111111";
const SECOND = "activity:v1:22222222222222222222222222222222";

function event(sequence, overrides = {}) {
    return {
        sequence,
        turn_id: "turn-public-0001",
        kind: "capability.started",
        phase: "capability",
        status: "running",
        label: "Consultando contactos",
        resource: null,
        capability: "odoo.query_records",
        progress: null,
        diagnostic_code: null,
        occurred_at: `2026-08-29T10:00:0${sequence}.000000Z`,
        activity_id: FIRST,
        ...overrides,
    };
}

test("started and completed lifecycle rows reduce to one semantic item", () => {
    const items = reduceSemanticActivity([
        event(1),
        event(2, { kind: "capability.completed", status: "completed" }),
    ]);

    expect(items).toHaveLength(1);
    expect(items[0].status).toBe("completed");
    expect(items[0].first_sequence).toBe(1);
    expect(items[0].last_sequence).toBe(2);
});

test("identical capabilities with different host activity ids remain separate", () => {
    const items = reduceSemanticActivity([event(1), event(2, { activity_id: SECOND })]);

    expect(items).toHaveLength(2);
    expect(items[0].activity_id).toBe(FIRST);
    expect(items[1].activity_id).toBe(SECOND);
});

test("failure updates the same work item and reconnect replay is idempotent", () => {
    const items = reduceSemanticActivity([
        event(1),
        event(1),
        event(2, {
            kind: "capability.failed",
            status: "failed",
            diagnostic_code: "capability_timeout",
        }),
    ]);

    expect(items).toHaveLength(1);
    expect(items[0].status).toBe("failed");
    expect(items[0].diagnostic_code).toBe("capability_timeout");
});

test("headline and completed step count ignore queue/finalization noise", () => {
    const presentation = semanticActivityPresentation([
        event(1, {
            phase: "queue",
            kind: "turn.started",
            activity_id: null,
            label: "Turn started",
        }),
        event(2),
        event(3, { kind: "capability.completed", status: "completed" }),
        event(4, {
            phase: "finalization",
            kind: "turn.completed",
            status: "completed",
            activity_id: null,
            label: "Turn completed",
        }),
    ]);

    expect(presentation.step_count).toBe(1);
    expect(presentation.headline.label).toBe("Consultando contactos");
    expect(presentation.items[0].status).toBe("completed");
});
