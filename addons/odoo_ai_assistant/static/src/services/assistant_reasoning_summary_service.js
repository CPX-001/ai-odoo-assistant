/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";
import { subscribeReasoningSummary } from "@odoo_ai_assistant/services/assistant_live_stream_client";

const HARD_MAX_REASONING_SUMMARY_CHARS = 8 * 1024;

export function reduceReasoningSummaryParts(parts, event, { maximumChars = HARD_MAX_REASONING_SUMMARY_CHARS } = {}) {
    const current = Array.isArray(parts) ? parts : [];
    if (
        !event ||
        !Number.isSafeInteger(event.sequence) ||
        event.sequence <= 0 ||
        typeof event.item_id !== "string" ||
        !Number.isSafeInteger(event.summary_index) ||
        typeof event.text !== "string" ||
        !event.text ||
        !Number.isSafeInteger(maximumChars) ||
        maximumChars < 128 ||
        maximumChars > HARD_MAX_REASONING_SUMMARY_CHARS
    ) {
        return current;
    }
    if (current.some((item) => item.sequences?.includes(event.sequence))) {
        return current;
    }
    const total = current.reduce((sum, item) => sum + (item.text?.length || 0), 0);
    const remaining = Math.max(0, maximumChars - total);
    if (!remaining) {
        return current;
    }
    const text = event.text.slice(0, remaining);
    const key = `${event.item_id}:${event.summary_index}`;
    const existingIndex = current.findIndex((item) => item.key === key);
    if (existingIndex < 0) {
        return [
            ...current,
            {
                key,
                item_id: event.item_id,
                summary_index: event.summary_index,
                text,
                sequences: [event.sequence],
            },
        ];
    }
    return current.map((item, index) =>
        index === existingIndex
            ? {
                  ...item,
                  text: `${item.text}${text}`.slice(0, maximumChars),
                  sequences: [...item.sequences, event.sequence].slice(-256),
              }
            : item
    );
}

function scopeForTurn(state, turnId) {
    if (!state.turnScopes || typeof state.turnScopes !== "object") {
        return null;
    }
    return Object.values(state.turnScopes).find((scope) => scope?.turnId === turnId) || null;
}

function projectReasoningSummary(state, scope) {
    if (!scope || state.activeTurnScopeKey !== scope.key) {
        return;
    }
    state.reasoningSummaryTurnId = scope.reasoningSummaryTurnId || null;
    state.reasoningSummaryParts = Array.isArray(scope.reasoningSummaryParts)
        ? [...scope.reasoningSummaryParts]
        : [];
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        const state = panel.state;
        state.reasoningSummaryTurnId = null;
        state.reasoningSummaryParts = [];

        subscribeReasoningSummary((event) => {
            if (!event || typeof event.turn_id !== "string") {
                return;
            }
            const scope = scopeForTurn(state, event.turn_id);
            if (scope) {
                if (scope.reasoningSummaryTurnId !== event.turn_id) {
                    scope.reasoningSummaryTurnId = event.turn_id;
                    scope.reasoningSummaryParts = [];
                }
                scope.reasoningSummaryParts = reduceReasoningSummaryParts(
                    scope.reasoningSummaryParts,
                    event
                );
                projectReasoningSummary(state, scope);
                return;
            }
            if (state.turnId && state.turnId !== event.turn_id) {
                return;
            }
            if (state.reasoningSummaryTurnId !== event.turn_id) {
                state.reasoningSummaryTurnId = event.turn_id;
                state.reasoningSummaryParts = [];
            }
            state.reasoningSummaryParts = reduceReasoningSummaryParts(
                state.reasoningSummaryParts,
                event
            );
        });

        return panel;
    },
});
