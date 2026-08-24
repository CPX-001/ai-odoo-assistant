/** @odoo-module **/

import { router } from "@web/core/browser/router";
import { registry } from "@web/core/registry";

const MAX_ODOO_ID = 2147483647;
const MAX_SELECTED_IDS = 8;
const ALLOWED_VIEW_TYPES = new Set([
    "activity",
    "calendar",
    "form",
    "graph",
    "kanban",
    "list",
    "pivot",
]);

function positiveId(value) {
    return Number.isSafeInteger(value) && value > 0 && value <= MAX_ODOO_ID ? value : null;
}

function viewIdHint(value) {
    if (typeof value === "string" && /^[1-9][0-9]{0,9}$/.test(value)) {
        return positiveId(Number(value));
    }
    return positiveId(value);
}

function modelName(value) {
    return typeof value === "string" && /^[A-Za-z_][A-Za-z0-9_.]{0,127}$/.test(value)
        ? value
        : null;
}

function selectedIds(value) {
    if (!Array.isArray(value)) {
        return [];
    }
    return [...new Set(value.map(positiveId).filter((id) => id !== null))].slice(
        0,
        MAX_SELECTED_IDS
    );
}

/**
 * Resolve the concrete Odoo view id for developer-facing UI only.
 * It is deliberately kept out of buildScreenContext(), so it is never promoted from a
 * browser hint into Assistant authority or sent to the Assistant Service.
 */
export function currentViewId(actionService, routerState = {}) {
    const controller = actionService?.currentController;
    const props = controller?.props || {};
    const currentState = controller?.currentState || {};
    const action = controller?.action || {};
    const directCandidates = [
        props.viewId,
        currentState.viewId,
        controller?.viewId,
        controller?.config?.viewId,
        routerState.view_id,
    ];
    for (const candidate of directCandidates) {
        const resolved = viewIdHint(candidate);
        if (resolved !== null) {
            return resolved;
        }
    }

    const viewType = props.type || routerState.view_type;
    if (Array.isArray(action.views) && typeof viewType === "string") {
        for (const entry of action.views) {
            if (!Array.isArray(entry) || entry.length < 2 || entry[1] !== viewType) {
                continue;
            }
            const resolved = viewIdHint(entry[0]);
            if (resolved !== null) {
                return resolved;
            }
        }
    }
    return null;
}

/**
 * Build an untrusted navigation hint from Odoo 18 action/menu/router state.
 * Identity, companies, sessions and credentials are deliberately absent.
 */
export function buildScreenContext(
    actionService,
    menuService,
    routerState = {},
    capturedAt = new Date()
) {
    const controller = actionService.currentController;
    const props = controller?.props || {};
    const action = controller?.action || {};
    const currentState = controller?.currentState || {};
    const viewTypeCandidate = props.type || routerState.view_type;
    const viewType = ALLOWED_VIEW_TYPES.has(viewTypeCandidate) ? viewTypeCandidate : null;
    const model = modelName(props.resModel || action.res_model || routerState.model);
    const formResId = positiveId(currentState.resId) || positiveId(props.resId);
    const resId = viewType === "form" ? formResId : null;
    const ids = resId
        ? [resId]
        : selectedIds(currentState.active_ids || routerState.active_ids);
    const currentApp = menuService.getCurrentApp?.();
    const menuId = positiveId(routerState.menu_id) || positiveId(currentApp?.id);
    const actionId = positiveId(controller?.config?.actionId) || positiveId(action.id);
    const allowedContextSubset = {};
    if (model && resId) {
        allowedContextSubset.active_model = model;
        allowedContextSubset.active_id = resId;
        allowedContextSubset.active_ids = [resId];
    }
    return {
        action_id: actionId,
        menu_id: menuId,
        view_type: viewType,
        model,
        res_id: resId,
        selected_ids: ids,
        allowed_context_subset: allowedContextSubset,
        captured_at: capturedAt.toISOString(),
    };
}

export const screenContextService = {
    dependencies: ["action", "menu"],
    start(env, { action, menu }) {
        return {
            capture() {
                return buildScreenContext(action, menu, router.current);
            },
            currentViewId() {
                return currentViewId(action, router.current);
            },
        };
    },
};

registry.category("services").add("odoo_ai_screen_context", screenContextService);
