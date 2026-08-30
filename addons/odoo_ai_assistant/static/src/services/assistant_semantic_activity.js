/** @odoo-module **/

const TERMINAL_STATUSES = new Set(["completed", "failed", "blocked", "cancelled"]);
const IMPORTANT_STATUSES = new Set(["failed", "blocked", "cancelled"]);
const TURN_TERMINAL_KINDS = new Set(["turn.completed", "turn.failed", "turn.cancelled"]);
const MEANINGFUL_PHASES = new Set([
    "provider",
    "answer",
    "capability",
    "retrieval",
    "preview",
    "approval",
    "execution",
    "verification",
]);
const DETAIL_LEVELS = new Set(["compact", "normal", "detailed", "diagnostic"]);
const REASONING_SUMMARY_LEVELS = new Set(["off", "concise", "detailed"]);
const DEFAULT_LIMITS = Object.freeze({
    max_rendered_activity_items: 100,
    max_rendered_batch_rows: 100,
    max_reasoning_summary_chars: 2000,
});

export const DEFAULT_ACTIVITY_PRESENTATION = Object.freeze({
    detail_level: "normal",
    transient_threshold_ms: 1200,
    batch_page_size: 5,
    show_technical_names: false,
    show_step_durations: false,
    reasoning_summary: "concise",
    limits: DEFAULT_LIMITS,
});

function timestamp(value) {
    const parsed = Date.parse(value || "");
    return Number.isFinite(parsed) ? parsed : null;
}

function itemKey(event) {
    if (event.semantic?.group_key) {
        return `semantic:${event.semantic.group_key}`;
    }
    return event.activity_id ? `activity:${event.activity_id}` : `event:${event.sequence}`;
}

function semanticCode(item) {
    if (IMPORTANT_STATUSES.has(item.status)) {
        if (item.status === "failed") {
            return "activity.failed";
        }
        if (item.status === "cancelled") {
            return "activity.cancelled";
        }
        return "activity.blocked";
    }
    if (item.headline_code) {
        return item.headline_code;
    }
    switch (item.phase) {
        case "provider":
            return "request.analysis";
        case "answer":
            return "answer.compose";
        case "retrieval":
            return "evidence.search";
        case "preview":
            return "capability.prepare";
        case "approval":
            return "approval.wait";
        case "execution":
            return "capability.execute";
        case "verification":
            return "capability.verify";
        case "capability":
            return "capability.use";
        case "queue":
            return "queue.wait";
        case "finalization":
            return "turn.finalize";
        default:
            return "activity.generic";
    }
}

function itemDurationMs(item) {
    const start = timestamp(item.started_at);
    const end = timestamp(item.ended_at);
    if (start === null || end === null) {
        return null;
    }
    return Math.max(0, end - start);
}

function freezeItem(item) {
    return Object.freeze({
        ...item,
        resource: item.resource || null,
        references: Object.freeze([...(item.references || [])]),
        headline_args: Object.freeze({ ...(item.headline_args || {}) }),
        progress_detail: item.progress_detail
            ? Object.freeze({ ...item.progress_detail })
            : null,
        result_summary: item.result_summary
            ? Object.freeze({
                  code: item.result_summary.code,
                  args: Object.freeze({ ...(item.result_summary.args || {}) }),
              })
            : null,
        lifecycle_activity_ids: Object.freeze([...(item.lifecycle_activity_ids || [])]),
        semantic_code: semanticCode(item),
        duration_ms: itemDurationMs(item),
    });
}

export function normalizeActivityPresentationPreferences(value) {
    const raw = value && typeof value === "object" ? value : {};
    const rawLimits = raw.limits && typeof raw.limits === "object" ? raw.limits : {};
    const maxItems = Number.isSafeInteger(rawLimits.max_rendered_activity_items)
        ? Math.min(Math.max(rawLimits.max_rendered_activity_items, 1), 100)
        : DEFAULT_LIMITS.max_rendered_activity_items;
    const maxBatchRows = Number.isSafeInteger(rawLimits.max_rendered_batch_rows)
        ? Math.min(Math.max(rawLimits.max_rendered_batch_rows, 1), 100)
        : DEFAULT_LIMITS.max_rendered_batch_rows;
    const maxSummaryChars = Number.isSafeInteger(rawLimits.max_reasoning_summary_chars)
        ? Math.min(Math.max(rawLimits.max_reasoning_summary_chars, 128), 8000)
        : DEFAULT_LIMITS.max_reasoning_summary_chars;
    return Object.freeze({
        detail_level: DETAIL_LEVELS.has(raw.detail_level) ? raw.detail_level : "normal",
        transient_threshold_ms:
            Number.isSafeInteger(raw.transient_threshold_ms) &&
            raw.transient_threshold_ms >= 0 &&
            raw.transient_threshold_ms <= 5000
                ? raw.transient_threshold_ms
                : 1200,
        batch_page_size:
            Number.isSafeInteger(raw.batch_page_size) &&
            raw.batch_page_size >= 1 &&
            raw.batch_page_size <= 20
                ? raw.batch_page_size
                : 5,
        show_technical_names: raw.show_technical_names === true,
        show_step_durations: raw.show_step_durations === true,
        reasoning_summary: REASONING_SUMMARY_LEVELS.has(raw.reasoning_summary)
            ? raw.reasoning_summary
            : "concise",
        limits: Object.freeze({
            max_rendered_activity_items: maxItems,
            max_rendered_batch_rows: maxBatchRows,
            max_reasoning_summary_chars: maxSummaryChars,
        }),
    });
}

function settleRunningItems(ordered, event) {
    if (
        event.phase !== "finalization" ||
        !TURN_TERMINAL_KINDS.has(event.kind) ||
        !["completed", "failed", "cancelled"].includes(event.status)
    ) {
        return;
    }
    for (const item of ordered) {
        if (item.status !== "running") {
            continue;
        }
        item.status = event.status;
        item.ended_at = event.occurred_at;
        item.last_sequence = Math.max(item.last_sequence, event.sequence);
        if (event.status === "failed") {
            item.diagnostic_code = item.diagnostic_code || event.diagnostic_code || null;
        }
    }
}

export function reduceSemanticActivity(events) {
    if (!Array.isArray(events)) {
        return Object.freeze([]);
    }
    const byKey = new Map();
    const ordered = [];
    const seenSequences = new Set();

    for (const event of events) {
        if (!event || !Number.isSafeInteger(event.sequence) || event.sequence <= 0) {
            continue;
        }
        if (seenSequences.has(event.sequence)) {
            continue;
        }
        seenSequences.add(event.sequence);
        settleRunningItems(ordered, event);
        const key = itemKey(event);
        const existing = byKey.get(key);
        if (!existing) {
            const created = {
                key,
                activity_id: event.activity_id || null,
                first_sequence: event.sequence,
                last_sequence: event.sequence,
                kind: event.kind,
                phase: event.phase,
                status: event.status,
                label: event.label,
                resource: event.resource || null,
                references: [...(event.references || [])],
                capability: event.capability || null,
                progress: event.progress ?? null,
                semantic_group_key: event.semantic?.group_key || null,
                parent_activity_id: event.semantic?.parent_activity_id || null,
                operation: event.semantic?.operation || null,
                headline_code: event.semantic?.headline_code || null,
                headline_args: { ...(event.semantic?.headline_args || {}) },
                progress_detail: event.semantic?.progress || null,
                result_summary: event.semantic?.result_summary || null,
                lifecycle_activity_ids: event.activity_id ? [event.activity_id] : [],
                diagnostic_code: event.diagnostic_code || null,
                started_at: event.occurred_at,
                ended_at: TERMINAL_STATUSES.has(event.status) ? event.occurred_at : null,
            };
            byKey.set(key, created);
            ordered.push(created);
            continue;
        }
        existing.last_sequence = event.sequence;
        existing.kind = event.kind;
        existing.phase = event.phase;
        existing.status = event.status;
        existing.label = event.label;
        existing.resource = event.resource || existing.resource || null;
        if (Array.isArray(event.references) && event.references.length) {
            existing.references = [...event.references];
        }
        existing.capability = event.capability || existing.capability || null;
        existing.progress = event.progress ?? existing.progress ?? null;
        existing.parent_activity_id =
            event.semantic?.parent_activity_id || existing.parent_activity_id || null;
        existing.operation = event.semantic?.operation || existing.operation || null;
        existing.headline_code = event.semantic?.headline_code || existing.headline_code || null;
        if (event.semantic?.headline_args) {
            existing.headline_args = { ...event.semantic.headline_args };
        }
        existing.progress_detail = event.semantic?.progress || existing.progress_detail || null;
        existing.result_summary =
            event.semantic?.result_summary || existing.result_summary || null;
        if (event.activity_id && !existing.lifecycle_activity_ids.includes(event.activity_id)) {
            existing.lifecycle_activity_ids.push(event.activity_id);
        }
        existing.diagnostic_code = event.diagnostic_code || existing.diagnostic_code || null;
        if (TERMINAL_STATUSES.has(event.status)) {
            existing.ended_at = event.occurred_at;
        }
    }

    return Object.freeze(ordered.map(freezeItem));
}

function visibleAtNormalDetail(item, preferences) {
    if (IMPORTANT_STATUSES.has(item.status) || item.phase === "approval") {
        return true;
    }
    if (!MEANINGFUL_PHASES.has(item.phase)) {
        return false;
    }
    if (
        item.phase === "verification" &&
        item.status === "completed" &&
        item.duration_ms !== null &&
        item.duration_ms < preferences.transient_threshold_ms
    ) {
        return false;
    }
    return true;
}

function selectByDetail(reduced, preferences) {
    if (preferences.detail_level === "diagnostic") {
        return [...reduced];
    }
    if (preferences.detail_level === "detailed") {
        return reduced.filter(
            (item) => MEANINGFUL_PHASES.has(item.phase) || IMPORTANT_STATUSES.has(item.status)
        );
    }
    const normal = reduced.filter((item) => visibleAtNormalDetail(item, preferences));
    const fallback = normal.length
        ? normal
        : reduced.filter((item) => MEANINGFUL_PHASES.has(item.phase));
    if (preferences.detail_level === "compact") {
        return fallback.length ? [fallback[fallback.length - 1]] : [];
    }
    return fallback;
}

function latestMeaningful(items) {
    for (let index = items.length - 1; index >= 0; index -= 1) {
        if (
            MEANINGFUL_PHASES.has(items[index].phase) ||
            IMPORTANT_STATUSES.has(items[index].status)
        ) {
            return items[index];
        }
    }
    return items.at(-1) || null;
}

function activityDurationMs(items) {
    const times = [];
    for (const item of items) {
        const start = timestamp(item.started_at);
        const end = timestamp(item.ended_at || item.started_at);
        if (start !== null) {
            times.push(start);
        }
        if (end !== null) {
            times.push(end);
        }
    }
    return times.length >= 2 ? Math.max(...times) - Math.min(...times) : 0;
}

export function semanticActivityPresentation(
    events,
    { running = false, preferences = DEFAULT_ACTIVITY_PRESENTATION } = {}
) {
    const normalizedPreferences = normalizeActivityPresentationPreferences(preferences);
    const reduced = reduceSemanticActivity(events);
    const normalVisible = reduced.filter((item) =>
        visibleAtNormalDetail(item, normalizedPreferences)
    );
    const semanticItems = normalVisible.length
        ? normalVisible
        : reduced.filter((item) => MEANINGFUL_PHASES.has(item.phase));
    const selected = selectByDetail(reduced, normalizedPreferences);
    const maxItems = normalizedPreferences.limits.max_rendered_activity_items;
    const truncated = selected.length > maxItems;
    const items = Object.freeze(selected.slice(-maxItems));
    const headline = latestMeaningful(semanticItems.length ? semanticItems : items);
    return Object.freeze({
        items,
        headline,
        step_count: semanticItems.length,
        duration_ms: Math.max(0, activityDurationMs(reduced)),
        running: Boolean(running),
        truncated,
        preferences: normalizedPreferences,
    });
}
