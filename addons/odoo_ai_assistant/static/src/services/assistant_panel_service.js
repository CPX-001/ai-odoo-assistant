/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { reactive } from "@odoo/owl";
import { normalizePublicTurnEvent } from "@odoo_ai_assistant/services/assistant_public_activity_contract";

const CHAT_WORKFLOWS = new Set(["AGENT"]);
const PLAN_STATES = new Set([
    "planning",
    "awaiting_confirmation",
    "authorized",
    "executing",
    "completed",
    "partial",
    "failed",
    "rejected",
    "expired",
]);
const TURN_TERMINAL_STATES = new Set([
    "completed",
    "failed",
    "cancelled",
    "recovery_required",
]);
const NON_RECOVERY_TERMINAL_STATES = new Set(["completed", "failed", "cancelled"]);
const ACTIVE_EXECUTION_PLAN_STATES = new Set(["authorized", "executing"]);
const MAX_NATIVE_POLL_ATTEMPTS = 360;
const NATIVE_POLL_DELAY_MS = 500;
const BACKGROUND_POLL_DELAY_MS = 5000;
const MAX_TRANSIENT_PLAN_POLL_FAILURES = 3;
const KNOWN_ERROR_CODES = new Set([
    "access_denied",
    "action_rejected",
    "agent_budget_exceeded",
    "authentication_failed",
    "capability_not_available",
    "capability_plan_approval_required",
    "capability_plan_binding_mismatch",
    "capability_plan_precondition_changed",
    "capability_plan_version_mismatch",
    "capability_verification_failed",
    "chat_store_unavailable",
    "codex_not_connected",
    "codex_unavailable",
    "engine_timeout",
    "engine_unavailable",
    "evidence_unavailable",
    "invalid_context",
    "invalid_response",
    "query_budget_exceeded",
    "query_rejected",
    "record_context_required",
    "runtime_unavailable",
    "service_unavailable",
    "worker_lost_after_write_barrier",
]);

function exactKeys(value, expected) {
    return (
        value !== null &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        Object.keys(value).sort().join("|") === [...expected].sort().join("|")
    );
}

function validJsonValue(value, depth = 0) {
    if (depth > 6) {
        return false;
    }
    if (value === null || typeof value === "boolean") {
        return true;
    }
    if (typeof value === "number") {
        return Number.isFinite(value);
    }
    if (typeof value === "string") {
        return value.length <= 4000;
    }
    if (Array.isArray(value)) {
        return value.length <= 64 && value.every((item) => validJsonValue(item, depth + 1));
    }
    if (typeof value === "object") {
        const entries = Object.entries(value);
        return (
            entries.length <= 64 &&
            entries.every(
                ([key, item]) =>
                    typeof key === "string" &&
                    key.length > 0 &&
                    key.length <= 128 &&
                    validJsonValue(item, depth + 1)
            )
        );
    }
    return false;
}

function validReceipt(receipt) {
    return (
        receipt === null ||
        (exactKeys(receipt, [
            "error_code",
            "evidence_id",
            "outcome",
            "record_id",
            "record_model",
        ]) &&
            typeof receipt.outcome === "string" &&
            (receipt.error_code === null || typeof receipt.error_code === "string") &&
            (receipt.evidence_id === null || typeof receipt.evidence_id === "string") &&
            ((receipt.record_id === null &&
                (receipt.record_model === null || typeof receipt.record_model === "string")) ||
                (Number.isSafeInteger(receipt.record_id) &&
                    receipt.record_id > 0 &&
                    typeof receipt.record_model === "string")))
    );
}

function validCapabilityStep(step) {
    return (
        exactKeys(step, [
            "approval",
            "capability",
            "effect_scope",
            "preview",
            "receipt",
            "risk",
            "state",
            "step_id",
            "summary",
            "title",
        ]) &&
        typeof step.step_id === "string" &&
        step.step_id.length > 0 &&
        typeof step.capability === "string" &&
        /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/.test(step.capability) &&
        typeof step.title === "string" &&
        step.title.length > 0 &&
        step.title.length <= 1000 &&
        typeof step.summary === "string" &&
        step.summary.length > 0 &&
        step.summary.length <= 500 &&
        ["planned", "previewed", "executing", "completed", "partial", "failed", "skipped"].includes(
            step.state
        ) &&
        ["low", "moderate", "high", "protected"].includes(step.risk) &&
        ["read_only", "internal_reversible", "internal_irreversible", "external"].includes(
            step.effect_scope
        ) &&
        ["none", "policy", "always"].includes(step.approval) &&
        exactKeys(step.preview, Object.keys(step.preview || {})) &&
        validJsonValue(step.preview) &&
        validReceipt(step.receipt)
    );
}

function validAgentPlan(plan) {
    return (
        exactKeys(plan, [
            "assumptions",
            "expires_at",
            "goal",
            "metadata",
            "plan_id",
            "policy",
            "requires_confirmation",
            "risk",
            "state",
            "steps",
        ]) &&
        typeof plan.plan_id === "string" &&
        PLAN_STATES.has(plan.state) &&
        ["low", "moderate", "high", "protected"].includes(plan.risk) &&
        typeof plan.goal === "string" &&
        plan.goal.length > 0 &&
        plan.goal.length <= 1000 &&
        Array.isArray(plan.assumptions) &&
        plan.assumptions.length <= 12 &&
        plan.assumptions.every((value) => typeof value === "string") &&
        Array.isArray(plan.steps) &&
        plan.steps.length <= 12 &&
        plan.steps.every(validCapabilityStep) &&
        typeof plan.requires_confirmation === "boolean" &&
        (plan.expires_at === null || typeof plan.expires_at === "string") &&
        plan.metadata !== null &&
        typeof plan.metadata === "object" &&
        !Array.isArray(plan.metadata) &&
        exactKeys(plan.policy, [
            "allow_synthetic_data",
            "confirmation_mode",
            "constrained_by",
            "max_auto_risk",
        ]) &&
        ["always_confirm", "risk_based", "protected_only"].includes(
            plan.policy.confirmation_mode
        ) &&
        ["low", "moderate", "high", "protected"].includes(plan.policy.max_auto_risk) &&
        typeof plan.policy.allow_synthetic_data === "boolean" &&
        Array.isArray(plan.policy.constrained_by) &&
        plan.policy.constrained_by.every((value) =>
            ["system_ceiling", "administrator", "user", "conversation"].includes(value)
        )
    );
}

function validTaskPlan(taskPlan) {
    if (taskPlan === null || taskPlan === undefined) {
        return true;
    }
    const legacyKeys = ["goal", "revision", "steps"];
    const currentKeys = ["goal", "revision", "revision_kind", "revision_summary", "steps"];
    const legacy = exactKeys(taskPlan, legacyKeys);
    if (!legacy && !exactKeys(taskPlan, currentKeys)) {
        return false;
    }
    const revisionKind = legacy
        ? taskPlan.revision === 1
            ? "initial"
            : "progress"
        : taskPlan.revision_kind;
    const revisionSummary = legacy ? "" : taskPlan.revision_summary;
    if (
        typeof taskPlan.goal !== "string" ||
        taskPlan.goal.trim().length < 1 ||
        taskPlan.goal.length > 1000 ||
        taskPlan.goal.includes("\0") ||
        !Number.isSafeInteger(taskPlan.revision) ||
        taskPlan.revision < 1 ||
        !["initial", "progress", "replan"].includes(revisionKind) ||
        typeof revisionSummary !== "string" ||
        revisionSummary.length > 512 ||
        revisionSummary.includes("\0") ||
        (taskPlan.revision === 1 && revisionKind !== "initial") ||
        (taskPlan.revision > 1 && revisionKind === "initial") ||
        (revisionKind === "replan" && !revisionSummary.trim()) ||
        !Array.isArray(taskPlan.steps) ||
        taskPlan.steps.length < 1 ||
        taskPlan.steps.length > 12
    ) {
        return false;
    }
    const knownStepIds = new Set();
    for (const step of taskPlan.steps) {
        if (
            !exactKeys(step, ["depends_on", "state", "step_id", "title"]) ||
            typeof step.step_id !== "string" ||
            step.step_id.length < 1 ||
            step.step_id.length > 128 ||
            knownStepIds.has(step.step_id) ||
            typeof step.title !== "string" ||
            step.title.trim().length < 1 ||
            step.title.length > 512 ||
            step.title.includes("\0") ||
            !["pending", "in_progress", "completed", "blocked", "skipped"].includes(
                step.state
            ) ||
            !Array.isArray(step.depends_on) ||
            step.depends_on.length > 11 ||
            new Set(step.depends_on).size !== step.depends_on.length ||
            step.depends_on.some(
                (dependency) =>
                    typeof dependency !== "string" || !knownStepIds.has(dependency)
            )
        ) {
            return false;
        }
        knownStepIds.add(step.step_id);
    }
    return true;
}

function validCitation(value) {
    return (
        value !== null &&
        typeof value === "object" &&
        typeof value.evidence_id === "string" &&
        value.evidence_id.length <= 64 &&
        typeof value.kind === "string"
    );
}

function errorCode(response, fallback = "invalid_response") {
    const code = response?.error?.code || response?.error_code;
    return KNOWN_ERROR_CODES.has(code) ? code : fallback;
}

export function actionExecutionPending(state) {
    if (
        state?.actionReceipt?.state === "recovery_required" ||
        state?.turnState === "recovery_required" ||
        NON_RECOVERY_TERMINAL_STATES.has(state?.turnState) ||
        ["completed", "partial", "failed", "rejected"].includes(
            state?.actionReceipt?.state
        )
    ) {
        return false;
    }
    return ACTIVE_EXECUTION_PLAN_STATES.has(state?.result?.plan?.state);
}

export function recoveryPending(state) {
    return (
        state?.actionReceipt?.state === "recovery_required" ||
        state?.turnState === "recovery_required" ||
        actionExecutionPending(state)
    );
}

export function normalizeChatResponse(response) {
    const limitations = response?.limitations;
    const citations = response?.citations || [];
    const plan = response?.plan;
    if (
        response?.ok === true &&
        typeof response.turn_id === "string" &&
        CHAT_WORKFLOWS.has(response.workflow) &&
        typeof response.answer === "string" &&
        response.answer.length > 0 &&
        response.answer.length <= 16384 &&
        ["high", "medium", "low"].includes(response.confidence) &&
        Array.isArray(limitations) &&
        limitations.length <= 8 &&
        limitations.every(
            (value) => typeof value === "string" && value.length > 0 && value.length <= 1024
        ) &&
        Array.isArray(citations) &&
        citations.length <= 24 &&
        citations.every(validCitation) &&
        validAgentPlan(plan) &&
        validTaskPlan(response.task_plan) &&
        (response.conversation_id === null ||
            response.conversation_id === undefined ||
            typeof response.conversation_id === "string")
    ) {
        return {
            result: { ...response, citations, plan },
            errorCode: null,
        };
    }
    return { result: null, errorCode: errorCode(response) };
}

export function normalizeActionDecisionResponse(response, planId) {
    if (
        exactKeys(response, ["ok", "plan", "plan_id", "response", "state"]) &&
        response.ok === true &&
        response.plan_id === planId &&
        ["authorized", "rejected"].includes(response.state) &&
        validAgentPlan(response.plan) &&
        (response.response === null || normalizeChatResponse(response.response).result !== null)
    ) {
        return { receipt: response, plan: response.plan, response: response.response, errorCode: null };
    }
    return { receipt: null, plan: null, response: null, errorCode: errorCode(response) };
}

export function normalizeCapabilityPlanStatus(response, planId) {
    if (
        exactKeys(response, [
            "error_code",
            "ok",
            "plan",
            "plan_id",
            "response",
            "state",
            "turn_state",
        ]) &&
        response.ok === true &&
        response.plan_id === planId &&
        typeof response.state === "string" &&
        typeof response.turn_state === "string" &&
        (response.plan === null || validAgentPlan(response.plan)) &&
        (response.response === null || normalizeChatResponse(response.response).result !== null) &&
        (response.error_code === null || typeof response.error_code === "string")
    ) {
        return { status: response, errorCode: null };
    }
    return { status: null, errorCode: errorCode(response) };
}

export function normalizeHistoryResponse(response) {
    if (
        response?.ok === true &&
        (response.active_turn === null ||
            (typeof response.active_turn?.turn_id === "string" &&
                typeof response.active_turn?.state === "string")) &&
        (response.active_conversation_id === null ||
            typeof response.active_conversation_id === "string") &&
        Array.isArray(response.conversations) &&
        response.conversations.length <= 50 &&
        response.conversations.every(
            (item) =>
                typeof item?.conversation_id === "string" &&
                typeof item?.title === "string" &&
                typeof item?.updated_at === "string"
        ) &&
        Array.isArray(response.messages) &&
        response.messages.length <= 80 &&
        response.messages.every(validHistoryMessage)
    ) {
        return {
            history: {
                ...response,
                messages: response.messages.map((item) => ({
                    ...item,
                    ...(item.activity
                        ? { activity: normalizeHistoryActivity(item.activity) }
                        : {}),
                })),
            },
            errorCode: null,
        };
    }
    return { history: null, errorCode: errorCode(response) };
}

function validHistoryMessage(item) {
    if (
        typeof item?.message_id !== "string" ||
        !["user", "assistant"].includes(item?.role) ||
        typeof item?.content !== "string" ||
        typeof item?.created_at !== "string"
    ) {
        return false;
    }
    if (!Object.hasOwn(item, "activity")) {
        return true;
    }
    return item.role === "assistant" && normalizeHistoryActivity(item.activity) !== null;
}

function normalizeHistoryActivity(value) {
    if (
        !exactKeys(value, ["turn_id", "events", "reasoning_summary_parts"]) ||
        typeof value.turn_id !== "string" ||
        !Array.isArray(value.events) ||
        value.events.length > 100 ||
        !Array.isArray(value.reasoning_summary_parts) ||
        value.reasoning_summary_parts.length > 65
    ) {
        return null;
    }
    const events = value.events.map(normalizePublicTurnEvent);
    if (events.some((event) => !event || event.turn_id !== value.turn_id)) {
        return null;
    }
    let total = 0;
    const parts = [];
    for (const part of value.reasoning_summary_parts) {
        if (
            !exactKeys(part, ["key", "text"]) ||
            typeof part.key !== "string" ||
            !/^[A-Za-z0-9_.:-]{3,320}$/.test(part.key) ||
            typeof part.text !== "string" ||
            !part.text ||
            part.text.includes("\u0000")
        ) {
            return null;
        }
        total += part.text.length;
        if (total > 8 * 1024) {
            return null;
        }
        parts.push(Object.freeze({ key: part.key, text: part.text }));
    }
    return Object.freeze({
        turn_id: value.turn_id,
        events: Object.freeze(events),
        reasoning_summary_parts: Object.freeze(parts),
    });
}

export function normalizeRuntimeStatus(response) {
    if (
        exactKeys(response, ["can_configure", "ok", "requires_setup", "state"]) &&
        response.ok === true &&
        [
            "authenticated",
            "authentication_error",
            "codex_unavailable",
            "login_pending",
            "not_authenticated",
        ].includes(response.state) &&
        typeof response.requires_setup === "boolean" &&
        typeof response.can_configure === "boolean" &&
        response.requires_setup === (response.state !== "authenticated")
    ) {
        return response;
    }
    return null;
}

function browserStorage() {
    try {
        return globalThis.localStorage || null;
    } catch {
        return null;
    }
}

export function draftStorageKey(conversationId) {
    const host = globalThis.location?.host || "odoo";
    const uid = globalThis.odoo?.session_info?.uid ?? globalThis.odoo?.__session_info__?.uid;
    const userScope = Number.isSafeInteger(uid) && uid > 0 ? String(uid) : "session";
    return `odoo_ai_assistant:draft:${host}:${userScope}:${conversationId || "new"}`;
}

export function loadDraft(storage, conversationId) {
    try {
        const value = storage?.getItem(draftStorageKey(conversationId));
        return typeof value === "string" ? value.slice(0, 4000) : "";
    } catch {
        return "";
    }
}

export function saveDraft(storage, conversationId, value) {
    try {
        storage?.setItem(draftStorageKey(conversationId), String(value || "").slice(0, 4000));
        return true;
    } catch {
        return false;
    }
}

export function resetForNewConversation(state, storage) {
    saveDraft(storage, state.conversationId, state.draft);
    state.conversationId = null;
    state.activeTurn = null;
    state.messages = [];
    state.draft = "";
    state.result = null;
    state.actionReceipt = null;
    state.actionStatusConnectionInterrupted = false;
    state.turnState = null;
    state.taskPlanRequested = false;
    state.errorCode = null;
    saveDraft(storage, null, "");
}

function requestId() {
    const uuid = globalThis.crypto?.randomUUID?.();
    if (typeof uuid === "string" && uuid.length >= 8) {
        return uuid;
    }
    return `web-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

function appendAssistantMessage(state, response, suffix) {
    if (!response?.answer || !response?.turn_id) {
        return;
    }
    const last = state.messages[state.messages.length - 1];
    if (last?.role === "assistant" && last.content === response.answer) {
        return;
    }
    state.messages = [
        ...state.messages,
        {
            message_id: `local-assistant-${response.turn_id}-${suffix}`,
            role: "assistant",
            content: response.answer,
            created_at: new Date().toISOString(),
        },
    ];
}

async function pollTurnResponse({ rpcCall, turnId, waitCall }) {
    for (let attempt = 0; attempt < MAX_NATIVE_POLL_ATTEMPTS; attempt += 1) {
        await waitCall(NATIVE_POLL_DELAY_MS);
        const status = await rpcCall("/odoo_ai/v1/turn/status", {
            turn_id: turnId,
            after_sequence: 0,
        });
        if (status?.ok !== true || status.turn_id !== turnId) {
            throw new Error(errorCode(status, "runtime_unavailable"));
        }
        if (["completed", "awaiting_confirmation"].includes(status.state)) {
            const normalized = normalizeChatResponse(status.response);
            if (!normalized.result) {
                throw new Error(normalized.errorCode || "invalid_response");
            }
            return normalized.result;
        }
        if (TURN_TERMINAL_STATES.has(status.state)) {
            throw new Error(status.error_code || "runtime_unavailable");
        }
    }
    throw new Error("engine_timeout");
}

export async function submitAssistantRequest({
    state,
    screenContext,
    rpcCall,
    message,
    waitCall = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
}) {
    if (state.loading || state.decisionLoading || recoveryPending(state)) {
        return false;
    }
    const normalized = typeof message === "string" ? message.trim() : "";
    if (!normalized || normalized.length > 4000) {
        state.errorCode = "invalid_context";
        return false;
    }
    state.context = screenContext.capture();
    state.loading = true;
    state.errorCode = null;
    state.actionReceipt = null;
    state.actionStatusConnectionInterrupted = false;
    try {
        const queued = await rpcCall("/odoo_ai/v1/turn", {
            message: normalized,
            screen: state.context,
            conversation_id: state.conversationId,
            client_request_id: requestId(),
        });
        if (queued?.ok !== true || typeof queued.turn_id !== "string") {
            throw new Error(errorCode(queued, "runtime_unavailable"));
        }
        const result = ["completed", "awaiting_confirmation"].includes(queued.state)
            ? normalizeChatResponse(queued.response).result
            : await pollTurnResponse({ rpcCall, turnId: queued.turn_id, waitCall });
        if (!result) {
            throw new Error("invalid_response");
        }
        state.result = result;
        state.conversationId = result.conversation_id || state.conversationId;
        state.messages = [
            ...state.messages,
            {
                message_id: `local-user-${result.turn_id}`,
                role: "user",
                content: normalized,
                created_at: new Date().toISOString(),
            },
            {
                message_id: `local-assistant-${result.turn_id}`,
                role: "assistant",
                content: result.answer,
                created_at: new Date().toISOString(),
            },
        ];
        return true;
    } catch (error) {
        state.result = null;
        state.errorCode = KNOWN_ERROR_CODES.has(error?.message) ? error.message : "service_unavailable";
        return false;
    } finally {
        state.loading = false;
    }
}

export async function loadChatHistory({ state, rpcCall, conversationId = state.conversationId }) {
    if (state.historyLoading) {
        return false;
    }
    state.historyLoading = true;
    try {
        const response = await rpcCall("/odoo_ai/v1/chat-history", {
            conversation_id: conversationId,
        });
        const parsed = normalizeHistoryResponse(response);
        if (!parsed.history) {
            state.errorCode = parsed.errorCode;
            return false;
        }
        state.conversations = parsed.history.conversations;
        state.conversationId = parsed.history.active_conversation_id;
        state.messages = parsed.history.messages;
        state.activeTurn = parsed.history.active_turn;
        state.errorCode = null;
        return true;
    } catch {
        state.errorCode = "service_unavailable";
        return false;
    } finally {
        state.historyLoading = false;
    }
}

export async function loadAgentPolicy({ state, rpcCall }) {
    state.policyLoading = true;
    try {
        const response = await rpcCall("/odoo_ai/v1/agent-policy", {});
        if (
            response?.ok === true &&
            ["always_confirm", "risk_based", "protected_only"].includes(
                response.confirmation_mode
            ) &&
            ["low", "moderate", "high"].includes(response.max_auto_risk)
        ) {
            state.agentPolicy = {
                confirmation_mode: response.confirmation_mode,
                max_auto_risk: response.max_auto_risk,
            };
            return true;
        }
        state.errorCode = "invalid_response";
        return false;
    } catch {
        state.errorCode = "service_unavailable";
        return false;
    } finally {
        state.policyLoading = false;
    }
}

export async function loadRuntimeStatus({ state, rpcCall }) {
    state.runtimeLoading = true;
    try {
        const status = normalizeRuntimeStatus(
            await rpcCall("/odoo_ai/v1/runtime-status", {})
        );
        if (!status) {
            state.runtimeState = "authentication_error";
            state.runtimeCanConfigure = false;
            return false;
        }
        state.runtimeState = status.state;
        state.runtimeCanConfigure = status.can_configure;
        return true;
    } catch {
        state.runtimeState = "authentication_error";
        state.runtimeCanConfigure = false;
        return false;
    } finally {
        state.runtimeLoading = false;
    }
}

export async function saveAgentPolicy({ state, rpcCall, confirmationMode, maxAutoRisk }) {
    if (
        state.policyLoading ||
        !["always_confirm", "risk_based", "protected_only"].includes(confirmationMode) ||
        !["low", "moderate", "high"].includes(maxAutoRisk)
    ) {
        return false;
    }
    state.policyLoading = true;
    try {
        const response = await rpcCall("/odoo_ai/v1/agent-policy-set", {
            confirmation_mode: confirmationMode,
            max_auto_risk: maxAutoRisk,
        });
        if (response?.ok !== true) {
            state.errorCode = "invalid_response";
            return false;
        }
        state.agentPolicy = {
            confirmation_mode: response.confirmation_mode,
            max_auto_risk: response.max_auto_risk,
        };
        state.errorCode = null;
        return true;
    } catch {
        state.errorCode = "service_unavailable";
        return false;
    } finally {
        state.policyLoading = false;
    }
}

function terminalPlanProjection(plan, turnState) {
    if (!plan || !["failed", "cancelled"].includes(turnState)) {
        return plan;
    }
    const planState = turnState === "cancelled" ? "rejected" : "failed";
    return {
        ...plan,
        state: planState,
        steps: plan.steps.map((step) =>
            step.state === "executing" ? { ...step, state: "failed" } : step
        ),
    };
}

async function applyPlanStatus(state, rawStatus, planId) {
    const normalized = normalizeCapabilityPlanStatus(rawStatus, planId);
    if (!normalized.status) {
        state.errorCode = normalized.errorCode;
        return false;
    }
    const status = normalized.status;
    state.turnState = status.turn_state;
    const projectedPlan = terminalPlanProjection(status.plan, status.turn_state);
    if (projectedPlan && state.result) {
        state.result = { ...state.result, plan: projectedPlan };
    }
    if (status.turn_state === "completed" && status.response) {
        const parsed = normalizeChatResponse(status.response);
        if (!parsed.result) {
            state.errorCode = parsed.errorCode;
            return false;
        }
        state.result = parsed.result;
        state.actionReceipt = {
            ok: true,
            plan_id: planId,
            state: parsed.result.plan.state,
            plan: parsed.result.plan,
            response: parsed.result,
        };
        appendAssistantMessage(state, parsed.result, "final");
        state.errorCode = null;
        return true;
    }
    if (status.turn_state === "recovery_required") {
        state.actionReceipt = {
            ok: true,
            plan_id: planId,
            state: "recovery_required",
            plan: projectedPlan,
            response: null,
        };
        state.errorCode = status.error_code || "worker_lost_after_write_barrier";
        return true;
    }
    if (["failed", "cancelled"].includes(status.turn_state)) {
        state.actionReceipt = {
            ok: true,
            plan_id: planId,
            state: "failed",
            plan: projectedPlan,
            response: null,
        };
        state.errorCode = status.error_code || "runtime_unavailable";
        return true;
    }
    return null;
}

async function pollCapabilityPlan({
    state,
    rpcCall,
    planId,
    waitCall,
    once = false,
    onStateChange = () => {},
}) {
    let transientFailures = 0;
    for (let attempt = 0; once || actionExecutionPending(state); attempt += 1) {
        if (!once || attempt > 0) {
            await waitCall(
                attempt < MAX_NATIVE_POLL_ATTEMPTS
                    ? NATIVE_POLL_DELAY_MS
                    : BACKGROUND_POLL_DELAY_MS
            );
        }
        try {
            const status = await rpcCall("/odoo_ai/v1/turn/plan-status", { plan_id: planId });
            const terminal = await applyPlanStatus(state, status, planId);
            if (terminal === false) {
                if (once) {
                    return false;
                }
                transientFailures += 1;
                state.actionStatusConnectionInterrupted =
                    transientFailures > MAX_TRANSIENT_PLAN_POLL_FAILURES;
                onStateChange();
                continue;
            }
            transientFailures = 0;
            state.actionStatusConnectionInterrupted = false;
            if (terminal === null) {
                state.errorCode = null;
            }
            onStateChange();
            if (terminal === true) {
                return terminal;
            }
        } catch (error) {
            if (once) {
                throw error;
            }
            transientFailures += 1;
            state.actionStatusConnectionInterrupted =
                transientFailures > MAX_TRANSIENT_PLAN_POLL_FAILURES;
            onStateChange();
            continue;
        }
        if (once) {
            return false;
        }
    }
    return false;
}

export async function submitActionDecision({
    state,
    rpcCall,
    decision,
    waitCall = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
    onStateChange = () => {},
}) {
    const planId = state.result?.plan?.plan_id;
    if (
        state.loading ||
        state.decisionLoading ||
        recoveryPending(state) ||
        state.result?.plan?.state !== "awaiting_confirmation" ||
        typeof planId !== "string" ||
        !["approve", "reject"].includes(decision)
    ) {
        return false;
    }
    state.decisionLoading = true;
    state.errorCode = null;
    state.actionStatusConnectionInterrupted = false;
    onStateChange();
    try {
        const response = await rpcCall("/odoo_ai/v1/turn/plan-decision", {
            plan_id: planId,
            decision,
        });
        const normalized = normalizeActionDecisionResponse(response, planId);
        if (!normalized.receipt) {
            state.errorCode = normalized.errorCode;
            return false;
        }
        state.actionReceipt = normalized.receipt;
        if (normalized.plan && state.result) {
            state.result = { ...state.result, plan: normalized.plan };
        }
        if (decision === "reject") {
            const parsed = normalizeChatResponse(normalized.response);
            if (!parsed.result) {
                state.errorCode = parsed.errorCode;
                return false;
            }
            state.result = parsed.result;
            state.turnState = "completed";
            appendAssistantMessage(state, parsed.result, "rejected");
            onStateChange();
            return true;
        }
        // Approval has already been durably accepted. Stop presenting the confirmation button as
        // busy while the same operation is followed automatically in the background.
        state.turnState = "running";
        state.decisionLoading = false;
        state.actionStatusConnectionInterrupted = false;
        onStateChange();
        return await pollCapabilityPlan({
            state,
            rpcCall,
            planId,
            waitCall,
            onStateChange,
        });
    } catch (error) {
        state.actionReceipt = null;
        state.errorCode = KNOWN_ERROR_CODES.has(error?.message) ? error.message : "service_unavailable";
        return false;
    } finally {
        state.decisionLoading = false;
        onStateChange();
    }
}

export async function submitActionRetry({
    state,
    rpcCall,
    waitCall = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
    onStateChange = () => {},
}) {
    const planId = state.result?.plan?.plan_id;
    if (
        state.loading ||
        state.decisionLoading ||
        !recoveryPending(state) ||
        typeof planId !== "string"
    ) {
        return false;
    }
    state.decisionLoading = true;
    onStateChange();
    try {
        // Recovery never executes a capability from the browser. This is status-only;
        // a recovery_required turn remains host-controlled until a safe recovery path exists.
        return await pollCapabilityPlan({
            state,
            rpcCall,
            planId,
            waitCall,
            once: true,
            onStateChange,
        });
    } catch {
        state.errorCode = "service_unavailable";
        return false;
    } finally {
        state.decisionLoading = false;
        onStateChange();
    }
}

export const assistantPanelService = {
    dependencies: ["odoo_ai_screen_context"],
    start(env, { odoo_ai_screen_context: screenContext }) {
        const storage = browserStorage();
        const state = reactive({
            isOpen: false,
            loading: false,
            historyLoading: false,
            decisionLoading: false,
            policyLoading: false,
            runtimeLoading: true,
            runtimeState: null,
            runtimeCanConfigure: false,
            context: null,
            conversations: [],
            conversationId: null,
            activeTurn: null,
            messages: [],
            draft: loadDraft(storage, null),
            result: null,
            actionReceipt: null,
            actionStatusConnectionInterrupted: false,
            turnState: null,
            taskPlanRequested: false,
            agentPolicy: {
                confirmation_mode: "risk_based",
                max_auto_risk: "low",
            },
            errorCode: null,
        });
        const refreshContext = () => {
            state.context = screenContext.capture();
        };
        const syncDraft = () => {
            state.draft = loadDraft(storage, state.conversationId);
        };
        const loadHistory = async (conversationId = state.conversationId) => {
            const loaded = await loadChatHistory({ state, rpcCall: rpc, conversationId });
            if (loaded) {
                syncDraft();
            }
            return loaded;
        };
        const open = () => {
            state.isOpen = true;
            refreshContext();
            void loadHistory();
            void loadAgentPolicy({ state, rpcCall: rpc });
            void loadRuntimeStatus({ state, rpcCall: rpc });
        };
        return {
            state,
            open,
            close() {
                saveDraft(storage, state.conversationId, state.draft);
                state.isOpen = false;
            },
            toggle() {
                if (state.isOpen) {
                    saveDraft(storage, state.conversationId, state.draft);
                    state.isOpen = false;
                } else {
                    open();
                }
            },
            refreshContext,
            loadHistory,
            newConversation() {
                if (recoveryPending(state)) {
                    return false;
                }
                resetForNewConversation(state, storage);
                return true;
            },
            async selectConversation(conversationId) {
                if (
                    state.loading ||
                    state.decisionLoading ||
                    recoveryPending(state) ||
                    !conversationId
                ) {
                    return false;
                }
                saveDraft(storage, state.conversationId, state.draft);
                state.result = null;
                state.actionReceipt = null;
                return loadHistory(conversationId);
            },
            setDraft(value) {
                state.draft = String(value || "").slice(0, 4000);
                saveDraft(storage, state.conversationId, state.draft);
            },
            async submit(message) {
                if (state.runtimeState !== "authenticated") {
                    state.errorCode =
                        state.runtimeState === "codex_unavailable"
                            ? "codex_unavailable"
                            : "codex_not_connected";
                    return false;
                }
                const draftConversationId = state.conversationId;
                const sent = await submitAssistantRequest({
                    state,
                    screenContext,
                    rpcCall: rpc,
                    message,
                });
                if (sent) {
                    state.draft = "";
                    saveDraft(storage, draftConversationId, "");
                    saveDraft(storage, state.conversationId, "");
                }
                return sent;
            },
            async decide(decision) {
                return submitActionDecision({ state, rpcCall: rpc, decision });
            },
            async retry() {
                return submitActionRetry({ state, rpcCall: rpc });
            },
            async setAgentPolicy(confirmationMode, maxAutoRisk) {
                return saveAgentPolicy({
                    state,
                    rpcCall: rpc,
                    confirmationMode,
                    maxAutoRisk,
                });
            },
        };
    },
};

registry.category("services").add("odoo_ai_assistant_panel", assistantPanelService);
