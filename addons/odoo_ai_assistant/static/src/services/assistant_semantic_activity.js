/** @odoo-module **/

const TERMINAL_STATUSES = new Set(["completed", "failed", "blocked", "cancelled"]);
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

function timestamp(value) {
    const parsed = Date.parse(value || "");
    return Number.isFinite(parsed) ? parsed : null;
}

function itemKey(event) {
    return event.activity_id ? `activity:${event.activity_id}` : `event:${event.sequence}`;
}

function freezeItem(item) {
    return Object.freeze({
        ...item,
        resource: item.resource || null,
    });
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
                capability: event.capability || null,
                progress: event.progress ?? null,
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
        existing.capability = event.capability || existing.capability || null;
        existing.progress = event.progress ?? existing.progress ?? null;
        existing.diagnostic_code = event.diagnostic_code || existing.diagnostic_code || null;
        if (TERMINAL_STATUSES.has(event.status)) {
            existing.ended_at = event.occurred_at;
        }
    }

    return Object.freeze(ordered.slice(-100).map(freezeItem));
}

function latestMeaningful(items) {
    for (let index = items.length - 1; index >= 0; index -= 1) {
        if (MEANINGFUL_PHASES.has(items[index].phase)) {
            return items[index];
        }
    }
    return items.at(-1) || null;
}

export function semanticActivityPresentation(events, { running = false } = {}) {
    const reduced = reduceSemanticActivity(events);
    const meaningful = reduced.filter(
        (item) => MEANINGFUL_PHASES.has(item.phase) || ["failed", "blocked"].includes(item.status)
    );
    const items = meaningful.length ? Object.freeze(meaningful) : reduced;
    const headline = latestMeaningful(items);
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
    const durationMs = times.length >= 2 ? Math.max(...times) - Math.min(...times) : 0;
    return Object.freeze({
        items,
        headline,
        step_count: items.length,
        duration_ms: Math.max(0, durationMs),
        running: Boolean(running),
    });
}
