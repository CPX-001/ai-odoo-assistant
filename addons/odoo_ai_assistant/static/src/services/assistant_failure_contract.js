/** @odoo-module **/

const FAILURE_KEYS = [
    "code",
    "category",
    "stage",
    "component",
    "retryability",
    "effect_state",
    "user_action",
    "safe_summary",
    "safe_details",
    "diagnostic_id",
    "provider_code",
];
const CATEGORIES = new Set([
    "input",
    "context",
    "authentication",
    "provider_connection",
    "provider_protocol",
    "provider_capacity",
    "provider_output",
    "capability_discovery",
    "capability_input",
    "capability_execution",
    "capability_output",
    "policy",
    "approval",
    "odoo_access",
    "retrieval",
    "write_execution",
    "verification",
    "queue_worker",
    "persistence",
    "cancellation",
    "internal",
]);
const STAGES = new Set([
    "input",
    "context",
    "enqueue",
    "queue",
    "runtime",
    "provider",
    "reasoning",
    "capability",
    "retrieval",
    "policy",
    "approval",
    "execution",
    "verification",
    "persistence",
    "cancellation",
    "browser",
    "unknown",
]);
const COMPONENTS = new Set(["codex", "queue", "capability", "retrieval", "odoo", "browser"]);
const RETRYABILITIES = new Set(["never", "safe", "after_change", "unknown"]);
const EFFECT_STATES = new Set(["none", "not_started", "confirmed", "partial", "unknown"]);
const USER_ACTIONS = new Set([
    "retry",
    "reconnect",
    "clarify",
    "request_access",
    "review",
    "none",
]);
const CODE_RE = /^[a-z][a-z0-9_]{0,127}$/;
const DETAIL_KEY_RE = /^[a-z][a-z0-9_]{0,63}$/;
const DIAGNOSTIC_RE = /^[A-Za-z0-9_.:-]{8,128}$/;
const PROVIDER_CODE_RE = /^[A-Za-z][A-Za-z0-9_.:-]{0,63}$/;
const SENSITIVE_DETAIL_KEY_RE =
    /(?:auth|authorization|credential|password|prompt|secret|stderr|stdout|token)/i;
const MAX_DETAILS_BYTES = 4 * 1024;
const MAX_DETAILS_DEPTH = 4;
const MAX_DETAILS_ITEMS = 32;
const MAX_DETAIL_STRING = 1024;

function exactKeys(value, expected) {
    return (
        value !== null &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        Object.keys(value).sort().join("|") === [...expected].sort().join("|")
    );
}

function validDetailValue(value, depth = 0) {
    if (depth > MAX_DETAILS_DEPTH) {
        return false;
    }
    if (value === null || typeof value === "boolean") {
        return true;
    }
    if (typeof value === "number") {
        return Number.isFinite(value);
    }
    if (typeof value === "string") {
        return value.length <= MAX_DETAIL_STRING && !value.includes("\u0000");
    }
    if (Array.isArray(value)) {
        return (
            value.length <= MAX_DETAILS_ITEMS &&
            value.every((item) => validDetailValue(item, depth + 1))
        );
    }
    if (value !== null && typeof value === "object") {
        const entries = Object.entries(value);
        return (
            entries.length <= MAX_DETAILS_ITEMS &&
            entries.every(
                ([key, item]) =>
                    DETAIL_KEY_RE.test(key) &&
                    !SENSITIVE_DETAIL_KEY_RE.test(key) &&
                    validDetailValue(item, depth + 1)
            )
        );
    }
    return false;
}

function detailsWithinByteLimit(value) {
    try {
        return new TextEncoder().encode(JSON.stringify(value)).byteLength <= MAX_DETAILS_BYTES;
    } catch {
        return false;
    }
}

export function boundedFailureCode(value, fallback = "service_unavailable") {
    return typeof value === "string" && CODE_RE.test(value) ? value : fallback;
}

export function normalizeFailureEnvelope(value, expectedCode = null) {
    if (!exactKeys(value, FAILURE_KEYS)) {
        return null;
    }
    const summary =
        typeof value.safe_summary === "string"
            ? value.safe_summary.replace(/\s+/g, " ").trim()
            : "";
    if (
        !CODE_RE.test(value.code || "") ||
        (expectedCode !== null && value.code !== expectedCode) ||
        !CATEGORIES.has(value.category) ||
        !STAGES.has(value.stage) ||
        !COMPONENTS.has(value.component) ||
        !RETRYABILITIES.has(value.retryability) ||
        !EFFECT_STATES.has(value.effect_state) ||
        !USER_ACTIONS.has(value.user_action) ||
        summary.length < 1 ||
        summary.length > 512 ||
        value.safe_summary.includes("\u0000") ||
        !exactKeys(value.safe_details, Object.keys(value.safe_details || {})) ||
        !validDetailValue(value.safe_details) ||
        !detailsWithinByteLimit(value.safe_details) ||
        typeof value.diagnostic_id !== "string" ||
        !DIAGNOSTIC_RE.test(value.diagnostic_id) ||
        (value.provider_code !== null &&
            (typeof value.provider_code !== "string" ||
                !PROVIDER_CODE_RE.test(value.provider_code)))
    ) {
        return null;
    }
    return Object.freeze({
        code: value.code,
        category: value.category,
        stage: value.stage,
        component: value.component,
        retryability: value.retryability,
        effect_state: value.effect_state,
        user_action: value.user_action,
        safe_summary: summary,
        safe_details: Object.freeze({ ...value.safe_details }),
        diagnostic_id: value.diagnostic_id,
        provider_code: value.provider_code,
    });
}

export function failureCanRetry(failure) {
    return Boolean(
        failure &&
            failure.retryability === "safe" &&
            ["none", "not_started"].includes(failure.effect_state) &&
            failure.user_action === "retry"
    );
}

export function failureRequiresReview(failure) {
    return Boolean(
        failure &&
            (["partial", "unknown"].includes(failure.effect_state) ||
                failure.user_action === "review")
    );
}

export class AssistantFailureError extends Error {
    constructor(code, failure = null) {
        const boundedCode = boundedFailureCode(code, "runtime_unavailable");
        super(boundedCode);
        this.name = "AssistantFailureError";
        this.code = boundedCode;
        this.failure = failure;
    }
}

export function failureErrorFromStatus(status, fallback = "runtime_unavailable") {
    const legacyCode = boundedFailureCode(status?.error_code, fallback);
    const failure = normalizeFailureEnvelope(status?.failure, legacyCode);
    return new AssistantFailureError(failure?.code || legacyCode, failure);
}

export function failureFromError(error) {
    const code = boundedFailureCode(error?.code || error?.message, "service_unavailable");
    return {
        code,
        failure: normalizeFailureEnvelope(error?.failure, code),
    };
}
