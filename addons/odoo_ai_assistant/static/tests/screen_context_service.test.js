import { expect, test } from "@odoo/hoot";
import {
    buildScreenContext,
    currentViewId,
} from "@odoo_ai_assistant/services/screen_context_service";

const ACTION_ID = 42;
const MENU_ID = 7;
const CAPTURED_AT = new Date("2026-08-21T10:30:00.000Z");

function menuService() {
    return { getCurrentApp: () => ({ id: MENU_ID }) };
}

test("form view captures the current model and record from the action controller", () => {
    const actionService = {
        currentController: {
            action: { id: ACTION_ID, res_model: "sale.order" },
            config: { actionId: ACTION_ID },
            props: { resModel: "sale.order", resId: 41, type: "form" },
            currentState: { resId: 42 },
        },
    };

    const context = buildScreenContext(actionService, menuService(), {}, CAPTURED_AT);

    expect(context).toEqual({
        action_id: ACTION_ID,
        menu_id: MENU_ID,
        view_type: "form",
        model: "sale.order",
        res_id: 42,
        selected_ids: [42],
        allowed_context_subset: {
            active_id: 42,
            active_ids: [42],
            active_model: "sale.order",
        },
        captured_at: "2026-08-21T10:30:00.000Z",
    });
});

test("list view does not invent a current record", () => {
    const actionService = {
        currentController: {
            action: { id: ACTION_ID, res_model: "sale.order" },
            config: { actionId: ACTION_ID },
            props: { resModel: "sale.order", type: "list" },
            currentState: {},
        },
    };

    const context = buildScreenContext(actionService, menuService(), {}, CAPTURED_AT);

    expect(context.model).toBe("sale.order");
    expect(context.res_id).toBe(null);
    expect(context.selected_ids).toEqual([]);
    expect(context.allowed_context_subset).toEqual({});
});

test("captured payload contains navigation only and bounds selected ids", () => {
    const actionService = {
        currentController: {
            action: { id: ACTION_ID, res_model: "sale.order" },
            config: { actionId: ACTION_ID },
            props: { resModel: "sale.order", type: "list", viewId: 314 },
            currentState: { active_ids: [1, 2, 3, 4, 5, 6, 7, 8, 9] },
        },
    };

    const context = buildScreenContext(actionService, menuService(), {}, CAPTURED_AT);
    const serialized = JSON.stringify(context);

    expect(context.selected_ids).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(serialized).not.toInclude("view_id");
    expect(serialized).not.toInclude("uid");
    expect(serialized).not.toInclude("company");
    expect(serialized).not.toInclude("secret");
    expect(serialized).not.toInclude("token");
    expect(serialized).not.toInclude("session");
});

test("current view id is resolved for developer UI without entering screen context", () => {
    const direct = {
        currentController: {
            props: { type: "form", viewId: 314 },
            action: { views: [[99, "form"]] },
        },
    };
    expect(currentViewId(direct)).toBe(314);

    const fallback = {
        currentController: {
            props: { type: "list" },
            action: { views: [[271, "list"], [99, "form"]] },
        },
    };
    expect(currentViewId(fallback)).toBe(271);
    expect(currentViewId({ currentController: {} }, { view_id: "512" })).toBe(512);
    expect(currentViewId({ currentController: {} })).toBe(null);
});
