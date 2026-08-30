/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { assistantPanelService } from "@odoo_ai_assistant/services/assistant_panel_service";

const POLL_DELAY_MS = 500;
const TASK_STATES = new Set(["pending", "in_progress", "completed", "blocked", "skipped"]);
const REVISION_KINDS = new Set(["initial", "progress", "replan"]);

function exactKeys(value, expected) {
    return (
        value !== null &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        Object.keys(value).sort().join("|") === [...expected].sort().join("|")
    );
}

export function normalizeLiveTaskPlan(value) {
    if (value === null || value === undefined) {
        return null;
    }
    if (
        !exactKeys(value, ["goal", "revision", "revision_kind", "revision_summary", "steps"]) ||
        typeof value.goal !== "string" ||
        !value.goal.trim() ||
        value.goal.length > 1000 ||
        value.goal.includes("\0") ||
        !Number.isSafeInteger(value.revision) ||
        value.revision < 1 ||
        !REVISION_KINDS.has(value.revision_kind) ||
        typeof value.revision_summary !== "string" ||
        value.revision_summary.length > 512 ||
        value.revision_summary.includes("\0") ||
        (value.revision_kind === "replan" && !value.revision_summary.trim()) ||
        !Array.isArray(value.steps) ||
        value.steps.length < 1 ||
        value.steps.length > 12
    ) {
        return undefined;
    }
    const known = new Set();
    const steps = [];
    for (const step of value.steps) {
        if (
            !exactKeys(step, ["depends_on", "state", "step_id", "title"]) ||
            typeof step.step_id !== "string" ||
            !step.step_id ||
            step.step_id.length > 128 ||
            known.has(step.step_id) ||
            typeof step.title !== "string" ||
            !step.title.trim() ||
            step.title.length > 512 ||
            step.title.includes("\0") ||
            !TASK_STATES.has(step.state) ||
            !Array.isArray(step.depends_on) ||
            step.depends_on.length > 11 ||
            new Set(step.depends_on).size !== step.depends_on.length ||
            step.depends_on.some((dependency) => typeof dependency !== "string" || !known.has(dependency))
        ) {
            return undefined;
        }
        known.add(step.step_id);
        steps.push(Object.freeze({ ...step, depends_on: Object.freeze([...step.depends_on]) }));
    }
    return Object.freeze({
        goal: value.goal.trim(),
        revision: value.revision,
        revision_kind: value.revision_kind,
        revision_summary: value.revision_summary.trim(),
        steps: Object.freeze(steps),
    });
}

patch(assistantPanelService, {
    start(env, dependencies) {
        const panel = super.start(env, dependencies);
        const state = panel.state;
        const baseSubmit = panel.submit.bind(panel);
        const baseOpen = panel.open.bind(panel);
        const baseSelectConversation = panel.selectConversation?.bind(panel);
        const baseNewConversation = panel.newConversation?.bind(panel);
        let pollingGeneration = 0;

        state.liveTaskPlan = null;

        const activeScope = () => state.turnScopes?.[state.activeTurnScopeKey] || null;

        const refreshTaskPlan = async () => {
            const scope = activeScope();
            const turnId = scope?.turnId;
            if (typeof turnId !== "string" || !turnId) {
                return false;
            }
            const status = await rpc("/odoo_ai/v1/turn/status", {
                turn_id: turnId,
                after_sequence: 0,
            });
            if (status?.ok !== true || status.turn_id !== turnId) {
                return false;
            }
            const taskPlan = normalizeLiveTaskPlan(status.task_plan);
            if (taskPlan === undefined) {
                return false;
            }
            if (taskPlan && (!state.liveTaskPlan || taskPlan.revision >= state.liveTaskPlan.revision)) {
                state.liveTaskPlan = taskPlan;
            }
            return true;
        };

        const pollWhileActive = async () => {
            const generation = ++pollingGeneration;
            for (let attempt = 0; attempt < 360; attempt += 1) {
                if (generation !== pollingGeneration) {
                    return;
                }
                const scope = activeScope();
                if (!scope || !scope.loading || !scope.turnId) {
                    return;
                }
                try {
                    await refreshTaskPlan();
                } catch {
                    // Live TaskPlan is a presentation projection. Turn execution/status remains authoritative.
                }
                await new Promise((resolve) => setTimeout(resolve, POLL_DELAY_MS));
            }
        };

        panel.submit = async (message) => {
            state.liveTaskPlan = null;
            const pending = baseSubmit(message);
            void Promise.resolve().then(() => pollWhileActive());
            return pending;
        };

        panel.open = () => {
            baseOpen();
            void Promise.resolve().then(async () => {
                try {
                    await refreshTaskPlan();
                } catch {
                    // A missing live projection must not block opening the chat.
                }
                void pollWhileActive();
            });
        };

        if (baseSelectConversation) {
            panel.selectConversation = async (conversationId) => {
                pollingGeneration += 1;
                state.liveTaskPlan = null;
                const selected = await baseSelectConversation(conversationId);
                if (selected) {
                    try {
                        await refreshTaskPlan();
                    } catch {
                        // Presentation-only refresh.
                    }
                    void pollWhileActive();
                }
                return selected;
            };
        }

        if (baseNewConversation) {
            panel.newConversation = (...args) => {
                pollingGeneration += 1;
                state.liveTaskPlan = null;
                return baseNewConversation(...args);
            };
        }

        return panel;
    },
});
