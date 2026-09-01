import { expect, test } from "@odoo/hoot";
import {
    normalizeActivityPresentationPreferences,
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
        semantic: null,
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
    expect(items[0].semantic_code).toBe("capability.use");
});

test("a running turn is visible immediately before the first server activity", () => {
    const presentation = semanticActivityPresentation([], { running: true });

    expect(presentation.items).toHaveLength(1);
    expect(presentation.headline.semantic_code).toBe("request.analysis");
    expect(presentation.headline.status).toBe("running");
});

test("filtered queue retries never make running request analysis disappear", () => {
    const presentation = semanticActivityPresentation(
        [
            event(1, {
                phase: "queue",
                kind: "turn.started",
                activity_id: null,
                label: "Procesando petición",
            }),
            event(2, {
                phase: "queue",
                kind: "turn.started",
                activity_id: null,
                label: "Procesando petición",
            }),
        ],
        { running: true }
    );

    expect(presentation.items).toHaveLength(1);
    expect(presentation.headline.semantic_code).toBe("request.analysis");
    expect(presentation.headline.status).toBe("running");
});

test("a new semantic step settles the previous running step", () => {
    const items = reduceSemanticActivity([
        event(1, { phase: "provider", kind: "provider.started" }),
        event(2, {
            activity_id: SECOND,
            phase: "capability",
            kind: "capability.started",
        }),
    ]);

    expect(items).toHaveLength(2);
    expect(items[0].status).toBe("completed");
    expect(items[0].ended_at).toBe("2026-08-29T10:00:02.000000Z");
    expect(items[1].status).toBe("running");
    expect(items.filter((item) => item.status === "running")).toHaveLength(1);
});

test("identical capabilities with different host activity ids remain separate", () => {
    const items = reduceSemanticActivity([event(1), event(2, { activity_id: SECOND })]);

    expect(items).toHaveLength(2);
    expect(items[0].activity_id).toBe(FIRST);
    expect(items[1].activity_id).toBe(SECOND);
});

test("explicit host semantic grouping merges related lifecycle operations only", () => {
    const group = "semantic:v1:33333333333333333333333333333333";
    const semantic = {
        group_key: group,
        parent_activity_id: null,
        operation: "capability.prepare",
        headline_code: "activity.prepare.create",
        headline_args: { model_label: "Quotations", count: 200 },
        progress: null,
        result_summary: null,
    };
    const items = reduceSemanticActivity([
        event(1, { semantic }),
        event(2, { activity_id: SECOND, semantic, status: "completed", kind: "preview.completed" }),
    ]);

    expect(items).toHaveLength(1);
    expect(items[0].lifecycle_activity_ids).toEqual([FIRST, SECOND]);
    expect(items[0].semantic_code).toBe("activity.prepare.create");
    expect(items[0].headline_args.count).toBe(200);
});

test("normal semantic projection replaces raw technical titles with host codes", () => {
    const semantic = {
        group_key: null,
        parent_activity_id: null,
        operation: "odoo.records.query",
        headline_code: "activity.query.records",
        headline_args: { model_label: "Customers" },
        progress: null,
        result_summary: { code: "activity.result.records_found", args: { count: 12, model_label: "Customers" } },
    };
    const presentation = semanticActivityPresentation([
        event(1, { label: "Query Odoo records", semantic }),
        event(2, { label: "Query Odoo records", semantic, kind: "capability.completed", status: "completed" }),
    ]);

    expect(presentation.items).toHaveLength(1);
    expect(presentation.items[0].semantic_code).toBe("activity.query.records");
    expect(presentation.items[0].result_summary.args.count).toBe(12);
    expect(presentation.items[0].semantic_code).not.toBe("Query Odoo records");
});

test("grounded progress is preserved and absent when the host did not provide it", () => {
    const base = {
        group_key: null,
        parent_activity_id: null,
        operation: "capability.execute",
        headline_code: "activity.execute.create",
        headline_args: { model_label: "Quotations", count: 200 },
        progress: null,
        result_summary: null,
    };
    const items = reduceSemanticActivity([
        event(1, { semantic: base }),
        event(2, {
            activity_id: SECOND,
            semantic: { ...base, progress: { current: 50, total: 200 } },
        }),
    ]);

    expect(items[0].progress_detail).toBe(null);
    expect(items[1].progress_detail).toEqual({ current: 50, total: 200 });
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
    expect(items[0].semantic_code).toBe("activity.failed");
});

test("normal history replaces retry provider failures with one terminal failure", () => {
    const events = [
        event(1, {
            phase: "provider",
            kind: "turn.failed",
            status: "failed",
            diagnostic_code: "codex_turn_failed",
        }),
        event(2, {
            activity_id: SECOND,
            phase: "provider",
            kind: "turn.failed",
            status: "failed",
            diagnostic_code: "codex_turn_failed",
        }),
        event(3, {
            activity_id: null,
            phase: "finalization",
            kind: "turn.failed",
            status: "failed",
            diagnostic_code: "codex_turn_failed",
        }),
    ];

    const normal = semanticActivityPresentation(events, {
        preferences: { detail_level: "normal" },
    });
    const diagnostic = semanticActivityPresentation(events, {
        preferences: { detail_level: "diagnostic" },
    });

    expect(normal.items).toHaveLength(1);
    expect(normal.items[0].phase).toBe("finalization");
    expect(diagnostic.items).toHaveLength(3);
});

test("turn completion settles an unmatched running answer item", () => {
    const items = reduceSemanticActivity([
        event(1, {
            kind: "agent.answer.started",
            phase: "answer",
            activity_id: null,
            capability: null,
            label: "Redactando respuesta",
        }),
        event(2, {
            kind: "turn.completed",
            phase: "finalization",
            status: "completed",
            activity_id: null,
            capability: null,
            label: "Turn completed",
        }),
    ]);

    expect(items[0].phase).toBe("answer");
    expect(items[0].status).toBe("completed");
    expect(items[0].ended_at).toBe("2026-08-29T10:00:02.000000Z");
});

test("turn cancellation settles unmatched running work as cancelled", () => {
    const items = reduceSemanticActivity([
        event(1),
        event(2, {
            kind: "turn.cancelled",
            phase: "finalization",
            status: "cancelled",
            activity_id: null,
            capability: null,
            label: "Turn cancelled",
        }),
    ]);

    expect(items[0].status).toBe("cancelled");
    expect(items[0].semantic_code).toBe("activity.cancelled");
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
    expect(presentation.headline.semantic_code).toBe("capability.use");
    expect(presentation.items[0].status).toBe("completed");
});

test("sub-threshold verification stays diagnostic but is hidden from normal history", () => {
    const events = [
        event(1, {
            activity_id: SECOND,
            phase: "verification",
            kind: "verification.started",
            occurred_at: "2026-08-29T10:00:01.000000Z",
        }),
        event(2, {
            activity_id: SECOND,
            phase: "verification",
            kind: "verification.completed",
            status: "completed",
            occurred_at: "2026-08-29T10:00:01.100000Z",
        }),
        event(3, { occurred_at: "2026-08-29T10:00:02.000000Z" }),
    ];

    const normal = semanticActivityPresentation(events, {
        preferences: { detail_level: "normal", transient_threshold_ms: 1200 },
    });
    const diagnostic = semanticActivityPresentation(events, {
        preferences: { detail_level: "diagnostic", transient_threshold_ms: 1200 },
    });

    expect(normal.items.some((item) => item.phase === "verification")).toBe(false);
    expect(diagnostic.items.some((item) => item.phase === "verification")).toBe(true);
    expect(normal.step_count).toBe(1);
});

test("compact renders only the latest semantic item while preserving semantic step count", () => {
    const presentation = semanticActivityPresentation(
        [event(1), event(2, { activity_id: SECOND, phase: "preview", kind: "preview.started" })],
        { preferences: { detail_level: "compact" } }
    );

    expect(presentation.items).toHaveLength(1);
    expect(presentation.items[0].activity_id).toBe(SECOND);
    expect(presentation.step_count).toBe(2);
});

test("presentation preferences fail to bounded defaults", () => {
    const normalized = normalizeActivityPresentationPreferences({
        detail_level: "raw",
        transient_threshold_ms: 99_999,
        batch_page_size: 500,
        expanded_line_count: 200,
        reasoning_summary: "private",
        limits: { max_rendered_activity_items: 1000, max_reasoning_summary_chars: 99999 },
    });

    expect(normalized.detail_level).toBe("normal");
    expect(normalized.transient_threshold_ms).toBe(1200);
    expect(normalized.batch_page_size).toBe(5);
    expect(normalized.expanded_line_count).toBe(5);
    expect(normalized.reasoning_summary).toBe("concise");
    expect(normalized.limits.max_rendered_activity_items).toBe(100);
    expect(normalized.limits.max_reasoning_summary_chars).toBe(8000);
});
