/** @odoo-module **/

const KINDS = new Set([
    "turn.queued",
    "turn.started",
    "provider.connecting",
    "provider.connected",
    "agent.answer.started",
    "capability.started",
    "capability.completed",
    "capability.failed",
    "retrieval.started",
    "retrieval.completed",
    "preview.started",
    "preview.completed",
    "approval.required",
    "execution.started",
    "execution.completed",
    "verification.started",
    "verification.completed",
    "turn.completed",
    "turn.failed",
    "turn.cancelled",
]);
const PHASES = new Set([
    "queue",
    "provider",
    "answer",
    "capability",
    "retrieval",
    "preview",
    "approval",
    "execution",
    "verification",
    "finalization",
]);
const STATUSES = new Set([
    "pending",
    "running",
    "completed",
    "failed",
    "blocked",
    "cancelled",
]);
const NAVIGATION_KINDS = new Set([
    "odoo_model",
    "odoo_action",
    "odoo_view",
    "odoo_menu",
    "odoo_setting",
]);
const KEYS = [
    "sequence",
    "turn_id",
    "kind",
    "phase",
    "status",
    "label",
    "resource",
    "references",
    "capability",
    "progress",
    "diagnostic_code",
    "occurred_at",
    "activity_id",
];
const TURN_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/;
const MODEL_RE = /^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$/;
const FIELD_RE = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/;
const ACTIVITY_ID_RE = /^activity:v[1-9][0-9]*:[0-9a-f]{32}$/;
const DIAGNOSTIC_RE = /^[A-Za-z0-9_.:-]{1,128}$/;
const OCCURRED_AT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/;
const MAX_RESOURCE_RECORDS = 50;
const MAX_NAVIGATION_REFERENCES = 12;

function exactKeys(value, expected) {
    return (
        value !== null &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        Object.keys(value).sort().join("|") === [...expected].sort().join("|")
    );
}

function validLabel(value, maximum, { allowEmpty = false } = {}) {
    if (typeof value !== "string" || value.includes("\u0000")) {
        return false;
    }
    const normalized = value.replace(/\s+/g, " ").trim();
    return (allowEmpty || normalized.length >= 1) && normalized.length <= maximum;
}

function normalizeResource(value) {
    if (value === null) {
        return null;
    }
    if (!exactKeys(value, ["model", "record_ids", "display_names"])) {
        return undefined;
    }
    if (value.model !== null && (typeof value.model !== "string" || !MODEL_RE.test(value.model))) {
        return undefined;
    }
    if (
        !Array.isArray(value.record_ids) ||
        value.record_ids.length > MAX_RESOURCE_RECORDS ||
        value.record_ids.some((recordId) => !Number.isSafeInteger(recordId) || recordId <= 0) ||
        new Set(value.record_ids).size !== value.record_ids.length ||
        !Array.isArray(value.display_names) ||
        value.display_names.length > MAX_RESOURCE_RECORDS ||
        value.display_names.some((name) => !validLabel(name, 160)) ||
        (value.display_names.length && value.display_names.length !== value.record_ids.length) ||
        ((value.record_ids.length || value.display_names.length) && value.model === null)
    ) {
        return undefined;
    }
    return Object.freeze({
        model: value.model,
        record_ids: Object.freeze([...value.record_ids]),
        display_names: Object.freeze(
            value.display_names.map((name) => name.replace(/\s+/g, " ").trim())
        ),
    });
}

function normalizeNavigationReference(value) {
    if (!value || typeof value !== "object" || !NAVIGATION_KINDS.has(value.kind)) {
        return null;
    }
    if (!validLabel(value.label, 160) || !validLabel(value.description, 240, { allowEmpty: true })) {
        return null;
    }
    const expected = {
        odoo_model: ["kind", "label", "description", "model"],
        odoo_action: ["kind", "label", "description", "model", "action_id"],
        odoo_view: ["kind", "label", "description", "model", "view_id"],
        odoo_menu: ["kind", "label", "description", "model", "action_id", "menu_id"],
        odoo_setting: [
            "kind",
            "label",
            "description",
            "model",
            "action_id",
            "setting_field",
        ],
    }[value.kind];
    if (!exactKeys(value, expected) || typeof value.model !== "string" || !MODEL_RE.test(value.model)) {
        return null;
    }
    for (const key of ["action_id", "view_id", "menu_id"]) {
        if (Object.hasOwn(value, key) && (!Number.isSafeInteger(value[key]) || value[key] <= 0)) {
            return null;
        }
    }
    if (
        Object.hasOwn(value, "setting_field") &&
        (typeof value.setting_field !== "string" || !FIELD_RE.test(value.setting_field))
    ) {
        return null;
    }
    if (value.kind === "odoo_setting" && value.model !== "res.config.settings") {
        return null;
    }
    return Object.freeze({
        ...value,
        label: value.label.replace(/\s+/g, " ").trim(),
        description: value.description.replace(/\s+/g, " ").trim(),
    });
}

function normalizeReferences(value) {
    if (!Array.isArray(value) || value.length > MAX_NAVIGATION_REFERENCES) {
        return null;
    }
    const result = [];
    for (const raw of value) {
        const reference = normalizeNavigationReference(raw);
        if (!reference) {
            return null;
        }
        result.push(reference);
    }
    return Object.freeze(result);
}

export function normalizePublicTurnEvent(value) {
    if (!exactKeys(value, KEYS)) {
        return null;
    }
    const resource = normalizeResource(value.resource);
    const references = normalizeReferences(value.references);
    if (
        !Number.isSafeInteger(value.sequence) ||
        value.sequence <= 0 ||
        typeof value.turn_id !== "string" ||
        !TURN_ID_RE.test(value.turn_id) ||
        !KINDS.has(value.kind) ||
        value.kind === "agent.thinking" ||
        !PHASES.has(value.phase) ||
        !STATUSES.has(value.status) ||
        !validLabel(value.label, 240) ||
        resource === undefined ||
        references === null ||
        (value.capability !== null &&
            (typeof value.capability !== "string" || !MODEL_RE.test(value.capability))) ||
        (value.progress !== null &&
            (!Number.isSafeInteger(value.progress) || value.progress < 0 || value.progress > 100)) ||
        (value.diagnostic_code !== null &&
            (typeof value.diagnostic_code !== "string" ||
                !DIAGNOSTIC_RE.test(value.diagnostic_code))) ||
        typeof value.occurred_at !== "string" ||
        !OCCURRED_AT_RE.test(value.occurred_at) ||
        (value.activity_id !== null &&
            (typeof value.activity_id !== "string" || !ACTIVITY_ID_RE.test(value.activity_id)))
    ) {
        return null;
    }
    return Object.freeze({
        sequence: value.sequence,
        turn_id: value.turn_id,
        kind: value.kind,
        phase: value.phase,
        status: value.status,
        label: value.label.replace(/\s+/g, " ").trim(),
        resource,
        references,
        capability: value.capability,
        progress: value.progress,
        diagnostic_code: value.diagnostic_code,
        occurred_at: value.occurred_at,
        activity_id: value.activity_id,
    });
}

export function normalizePublicTurnEventBatch(
    value,
    { afterSequence = 0, maximum = 100 } = {}
) {
    if (
        !Number.isSafeInteger(afterSequence) ||
        afterSequence < 0 ||
        !Number.isSafeInteger(maximum) ||
        maximum < 1 ||
        maximum > 100 ||
        !Array.isArray(value) ||
        value.length > maximum
    ) {
        return null;
    }
    const events = [];
    let previous = afterSequence;
    let turnId = null;
    for (const raw of value) {
        const event = normalizePublicTurnEvent(raw);
        if (!event || event.sequence <= previous || (turnId !== null && event.turn_id !== turnId)) {
            return null;
        }
        events.push(event);
        previous = event.sequence;
        turnId = turnId || event.turn_id;
    }
    return Object.freeze(events);
}
