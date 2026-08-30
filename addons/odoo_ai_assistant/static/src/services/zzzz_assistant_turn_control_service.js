/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import {
    assistantPanelService,
    normalizeChatResponse,
} from "@odoo_ai_assistant/services/assistant_panel_service";

const FOLLOW_POLL_MS = 500;
const FOLLOW_MAX_ATTEMPTS = 360;
const BIND_WAIT_MS = 50;
const BIND_WAIT_ATTEMPTS = 40;
const CANCEL_POLL_MS = 250;
const CANCEL_POLL_ATTEMPTS = 40;
let interventionSequence = 0;

export function newClientInterventionId() {
    const random = globalThis.crypto?.randomUUID?.();
    if (typeof random === "string" && random.length >= 8) {
        return `ui:${random}`;
    }
    interventionSequence += 1;
    return `ui:${Date.now()}:${interventionSequence}`;
}

function activeScope(state) {
    return state.turnScopes?.[state.activeTurnScopeKey] || null;
}

function projectScope(state, scope) {
    if (!scope || state.turnScopes?.[state.activeTurnScopeKey] !== scope) {
        return;
    }
    for (const key of [
        "loading",
        "decisionLoading",
        "result",
        "actionReceipt",
        "errorCode",
        "failure",
        "streamingText",
        "activityEvents",
        "currentActivity",
        "lastSubmittedMessage",
        "messages",
    ]) {
        state[key] = scope[key];
    }
}

function validMessageView(value) {
    return Boolean(
        value &&
            typeof value.message_id === "string" &&
            ["user", "assistant"].includes(value.role) &&
            typeof value.content === "string" &&
            typeof value.created_at === "string"
    );
}

function appendMessageOnce(scope, message) {
    if (!validMessageView(message)) {
        return false;
    }
    if (!scope.messages.some((item) => item.message_id === message.message_id)) {
        scope.messages = [...scope.messages, message];
    }
    return true;
}

function appendInterruptedOnce(scope, answer) {
    if (typeof answer !== "string" || !answer) {
        return;
    }
    if (scope.messages.some((item) => item.role === "assistant" && item.content === answer)) {
        return;
    }
    scope.messages = [
        ...scope.messages,
        {
            message_id: `local-assistant-interrupted-${scope.turnId}`,
            role: "assistant",
            content: answer,
            created_at: new Date().toISOString(),
        },
    ];
}

export function composerActionMode({
    loading,
    draft,
    decisionLoading,
    recoveryPending,
    stopLoading,
    awaitingApproval = false,
}) {
    if (decisionLoading || recoveryPending || stopLoading) {
        return "disabled";
    }
    const hasText = typeof draft === "string" && Boolean(draft.trim());
    if (loading && !hasText) {
        return "stop";
    }
    if (hasText) {
        return loading || awaitingApproval ? "redirect" : "send";
    }
    return "disabled";
}

export function applyAcceptedStopState(scope, state) {
    if (!scope || !["cancel_requested", "cancelled"].includes(state)) {
        return false;
    }
    scope.turnState = state;
    if (state === "cancelled") {
        scope.stopRequested = false;
        scope.loading = false;
    }
    return true;
}

export function normalizeCancellationStatus(response, turnId) {
    if (
        response?.ok !== true ||
        response.turn_id !== turnId ||
        !["cancel_requested", "cancelled"].includes(response.state)
    ) {
        return null;
    }
    return response;
}

async function waitForTerminalCancellation(turnId, initialResponse) {
    let current = normalizeCancellationStatus(initialResponse, turnId);
    for (
        let attempt = 0;
        current?.state === "cancel_requested" && attempt < CANCEL_POLL_ATTEMPTS;
        attempt += 1
    ) {
        await wait(CANCEL_POLL_MS);
        const status = normalizeCancellationStatus(
            await rpc("/odoo_ai/v1/turn/status", {
                turn_id: turnId,
                after_sequence: 0,
            }),
            turnId
        );
        if (!status) {
            return null;
        }
        current = status;
    }
    return current;
}

export function normalizeRedirectResponse(response, turnId, clientInterventionId = null) {
    if (
        response?.ok !== true ||
        response.turn_id !== turnId ||
        !["queued", "running"].includes(response.state) ||
        !Number.isSafeInteger(response.sequence) ||
        response.sequence <= 0 ||
        typeof response.client_intervention_id !== "string" ||
        (clientInterventionId !== null && response.client_intervention_id !== clientInterventionId) ||
        typeof response.duplicate !== "boolean" ||
        !Number.isSafeInteger(response.resume_after_sequence) ||
        response.resume_after_sequence < 0 ||
        !validMessageView(response.message) ||
        response.message.role !== "user"
    ) {
        return null;
    }
    return response;
}

export function normalizeReversionResponse(response, turnId) {
    if (
        response?.ok !== true ||
        response.turn_id !== turnId ||
        response.state !== "reverted" ||
        !validMessageView(response.message) ||
        response.message.role !== "assistant"
    ) {
        return null;
    }
    const parsed = normalizeChatResponse(response.response);
    if (!parsed.result) {
        return null;
    }
    return { ...response, response: parsed.result };
}

function errorCode(response, fallback) {
    const value = response?.error?.code || response?.error_code;
    return typeof value === "string" && value ? value : fallback;
}

function noticeForError(code) {
    const messages = {
        turn_effect_already_committed: _t(
            "La acción ya estaba en su fase de ejecución y esta corrección no puede cambiarla. Puedes detener el procesamiento y revisar los cambios realizados."
        ),
        turn_not_redirectable: _t("Este procesamiento ya no admite nuevas indicaciones."),
        turn_redirect_budget_exceeded: _t("Se han acumulado demasiadas correcciones en este procesamiento."),
        turn_redirect_limit_exceeded: _t("Se ha alcanzado el límite de correcciones para este procesamiento."),
        turn_intervention_id_conflict: _t("La corrección no pudo confirmarse de forma segura. Vuelve a intentarlo."),
        turn_reversion_not_ready: _t("Esta operación todavía no está lista para revertirse."),
        turn_reversion_unavailable: _t("Estos cambios no tienen una reversión automática segura."),
        capability_compensation_precondition_changed: _t(
            "Los datos han cambiado desde la operación original. No los he sobrescrito; revisa el estado actual antes de revertir."
        ),
        capability_compensation_rejected: _t("Odoo no ha permitido revertir estos cambios con el estado o permisos actuales."),
    };
    return messages[code] || _t("No se pudo aplicar este control al procesamiento actual.");
}

function wait(milliseconds) {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForTurnBinding(scope) {
    for (let attempt = 0; attempt < BIND_WAIT_ATTEMPTS; attempt += 1) {
        if (typeof scope.turnId === "string" && scope.turnId) {
            return scope.turnId;
        }
        if (!scope.loading) {
            return null;
        }
        await wait(BIND_WAIT_MS);
    }
    return typeof scope.turnId === "string" && scope.turnId ? scope.turnId : null;
}

async function followExistingTurn(state, scope) {
    scope.loading = true;
    scope.streamingText = "";
    scope.activityEvents = [];
    scope.currentActivity = null;
    scope.errorCode = null;
    scope.failure = null;
    projectScope(state, scope);
    try {
        for (let attempt = 0; attempt < FOLLOW_MAX_ATTEMPTS; attempt += 1) {
            await wait(FOLLOW_POLL_MS);
            const status = await rpc("/odoo_ai/v1/turn/status", {
                turn_id: scope.turnId,
                after_sequence: 0,
            });
            if (status?.ok !== true || status.turn_id !== scope.turnId) {
                scope.errorCode = errorCode(status, "runtime_unavailable");
                return false;
            }
            scope.turnState = status.state;
            if (["completed", "awaiting_confirmation"].includes(status.state)) {
                const parsed = normalizeChatResponse(status.response);
                if (!parsed.result) {
                    scope.errorCode = parsed.errorCode || "invalid_response";
                    return false;
                }
                scope.result = parsed.result;
                scope.actionReceipt = null;
                scope.turnState =
                    parsed.result.plan?.state === "awaiting_confirmation"
                        ? "awaiting_confirmation"
                        : "completed";
                appendMessageOnce(scope, {
                    message_id: `local-assistant-${parsed.result.turn_id}-redirect`,
                    role: "assistant",
                    content: parsed.result.answer,
                    created_at: new Date().toISOString(),
                });
                return true;
            }
            if (status.state === "cancelled") {
                scope.turnState = "cancelled";
                scope.errorCode = null;
                scope.failure = null;
                appendInterruptedOnce(scope, status.answer);
                return true;
            }
            if (["failed", "recovery_required"].includes(status.state)) {
                scope.errorCode = status.error_code || "runtime_unavailable";
                scope.turnState = status.state;
                return false;
            }
        }
        scope.errorCode = "engine_timeout";
        return false;
    } catch {
        scope.errorCode = "service_unavailable";
        return false;
    } finally {
        scope.stopRequested = false;
        scope.loading = false;
        projectScope(state, scope);
    }
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const service = super.start(env, dependencies);
        const state = service.state;
        const baseSubmit = service.submit.bind(service);
        state.stopLoading = false;
        state.reversionLoading = false;
        state.reversionConfirmationOpen = false;
        state.turnControlNotice = "";

        service.submit = async (message) => {
            const scope = activeScope(state);
            const normalized = typeof message === "string" ? message.trim() : "";
            const awaitingApproval = scope?.result?.plan?.state === "awaiting_confirmation";
            if (scope?.loading || awaitingApproval) {
                if (!normalized || normalized.length > 4000) {
                    return false;
                }
                const turnId = scope.turnId || (scope.loading ? await waitForTurnBinding(scope) : null);
                if (!turnId) {
                    state.turnControlNotice = _t("El procesamiento todavía no está listo para recibir la corrección.");
                    return false;
                }
                const clientInterventionId = newClientInterventionId();
                try {
                    const raw = await rpc("/odoo_ai/v1/turn/redirect", {
                        turn_id: turnId,
                        message: normalized,
                        client_intervention_id: clientInterventionId,
                    });
                    const redirected = normalizeRedirectResponse(
                        raw,
                        turnId,
                        clientInterventionId
                    );
                    if (!redirected) {
                        const code = errorCode(raw, "invalid_response");
                        state.turnControlNotice = noticeForError(code);
                        scope.errorCode = null;
                        projectScope(state, scope);
                        return false;
                    }
                    appendMessageOnce(scope, redirected.message);
                    scope.turnState = redirected.state;
                    scope.errorCode = null;
                    scope.failure = null;
                    state.turnControlNotice = "";
                    projectScope(state, scope);
                    if (awaitingApproval) {
                        scope.result = null;
                        scope.actionReceipt = null;
                        return followExistingTurn(state, scope);
                    }
                    return true;
                } catch {
                    state.turnControlNotice = _t("No se pudo enviar la corrección al procesamiento actual.");
                    return false;
                }
            }

            const submittedScope = scope;
            const sent = await baseSubmit(message);
            if (!sent && submittedScope?.stopRequested) {
                submittedScope.stopRequested = false;
                submittedScope.loading = false;
                submittedScope.turnState = "cancelled";
                submittedScope.errorCode = null;
                submittedScope.failure = null;
                submittedScope.streamingText = "";
                projectScope(state, submittedScope);
                return true;
            }
            return sent;
        };

        service.stop = async () => {
            const scope = activeScope(state);
            if (!scope?.loading || state.stopLoading) {
                return false;
            }
            state.stopLoading = true;
            scope.stopRequested = true;
            state.turnControlNotice = "";
            try {
                const turnId = scope.turnId || (await waitForTurnBinding(scope));
                if (!turnId) {
                    scope.stopRequested = false;
                    state.turnControlNotice = _t("No se pudo identificar el procesamiento que debía detenerse.");
                    return false;
                }
                let response = normalizeCancellationStatus(
                    await rpc("/odoo_ai/v1/turn/cancel", { turn_id: turnId }),
                    turnId
                );
                if (!response) {
                    scope.stopRequested = false;
                    state.turnControlNotice = noticeForError(errorCode(response, "invalid_response"));
                    return false;
                }
                response = await waitForTerminalCancellation(turnId, response);
                if (!response) {
                    scope.stopRequested = false;
                    state.turnControlNotice = noticeForError("invalid_response");
                    return false;
                }
                applyAcceptedStopState(scope, response.state);
                scope.streamingText = "";
                scope.errorCode = null;
                scope.failure = null;
                if (response.response) {
                    const parsed = normalizeChatResponse(response.response);
                    if (parsed.result) {
                        scope.result = parsed.result;
                    }
                }
                appendInterruptedOnce(scope, response.answer);
                projectScope(state, scope);
                return true;
            } catch {
                scope.stopRequested = false;
                state.turnControlNotice = _t("No se pudo detener el procesamiento actual.");
                return false;
            } finally {
                state.stopLoading = false;
            }
        };

        service.revertLastAction = async () => {
            const scope = activeScope(state);
            if (
                !scope?.turnId ||
                scope.loading ||
                state.reversionLoading ||
                scope.result?.plan?.metadata?.reversion_state !== "available"
            ) {
                return false;
            }
            state.reversionLoading = true;
            state.turnControlNotice = "";
            try {
                const raw = await rpc("/odoo_ai/v1/turn/revert", { turn_id: scope.turnId });
                const reverted = normalizeReversionResponse(raw, scope.turnId);
                if (!reverted) {
                    const code = errorCode(raw, "invalid_response");
                    state.turnControlNotice = noticeForError(code);
                    return false;
                }
                scope.result = reverted.response;
                scope.actionReceipt = null;
                scope.errorCode = null;
                scope.failure = null;
                appendMessageOnce(scope, reverted.message);
                projectScope(state, scope);
                return true;
            } catch {
                state.turnControlNotice = _t("No se pudieron revertir los cambios.");
                return false;
            } finally {
                state.reversionLoading = false;
            }
        };

        return service;
    },
});
