/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

const MODEL_RE = /^[A-Za-z_][A-Za-z0-9_.]{0,127}$/;
const FIELD_RE = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/;
const VIEW_TYPES = new Set(["list", "form", "kanban", "calendar", "graph", "pivot", "activity"]);
const NAVIGATION_KINDS = new Set([
    "odoo_record",
    "odoo_model",
    "odoo_action",
    "odoo_view",
    "odoo_menu",
    "odoo_setting",
]);
const MAX_REFERENCES = 50;
const MAX_RENDERED_REFERENCES = 100;

function exactKeys(value, expected) {
    return (
        value !== null &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        Object.keys(value).sort().join("|") === [...expected].sort().join("|")
    );
}

function validLabel(value, maximum = 240) {
    return typeof value === "string" && !value.includes("\u0000") && value.trim().length <= maximum;
}

export function resourceReferences(resource) {
    if (
        !resource ||
        typeof resource !== "object" ||
        typeof resource.model !== "string" ||
        !MODEL_RE.test(resource.model) ||
        !Array.isArray(resource.record_ids) ||
        resource.record_ids.length > MAX_REFERENCES ||
        !Array.isArray(resource.display_names) ||
        (resource.display_names.length &&
            resource.display_names.length !== resource.record_ids.length)
    ) {
        return [];
    }
    return resource.record_ids.flatMap((recordId, index) => {
        if (!Number.isSafeInteger(recordId) || recordId <= 0) {
            return [];
        }
        const display = resource.display_names[index];
        const label =
            typeof display === "string" && display.trim()
                ? display.trim().slice(0, 160)
                : `#${recordId}`;
        return [
            Object.freeze({
                kind: "odoo_record",
                model: resource.model,
                record_id: recordId,
                label,
            }),
        ];
    });
}

export function resourceModelReference(resource) {
    if (
        !resource ||
        typeof resource !== "object" ||
        typeof resource.model !== "string" ||
        !MODEL_RE.test(resource.model)
    ) {
        return null;
    }
    return Object.freeze({ kind: "odoo_model", model: resource.model });
}

export function normalizeHostNavigationReference(value) {
    if (!value || typeof value !== "object" || !NAVIGATION_KINDS.has(value.kind)) {
        return null;
    }
    if (value.kind === "odoo_record") {
        if (
            !exactKeys(value, ["kind", "label", "model", "record_id"]) ||
            !validLabel(value.label, 160) ||
            !MODEL_RE.test(value.model) ||
            !Number.isSafeInteger(value.record_id) ||
            value.record_id <= 0
        ) {
            return null;
        }
        return Object.freeze({
            kind: value.kind,
            label: value.label.trim(),
            model: value.model,
            record_id: value.record_id,
        });
    }
    if (!validLabel(value.label, 160) || !validLabel(value.description, 240)) {
        return null;
    }
    const common = { kind: value.kind, label: value.label.trim(), description: value.description.trim() };
    if (value.kind === "odoo_model") {
        if (!exactKeys(value, ["kind", "label", "description", "model"]) || !MODEL_RE.test(value.model)) {
            return null;
        }
        return Object.freeze({ ...common, model: value.model });
    }
    if (value.kind === "odoo_action") {
        if (
            !exactKeys(value, ["kind", "label", "description", "model", "action_id"]) ||
            !MODEL_RE.test(value.model) ||
            !Number.isSafeInteger(value.action_id) ||
            value.action_id <= 0
        ) {
            return null;
        }
        return Object.freeze({ ...common, model: value.model, action_id: value.action_id });
    }
    if (value.kind === "odoo_view") {
        if (
            !exactKeys(value, ["kind", "label", "description", "model", "view_id"]) ||
            !MODEL_RE.test(value.model) ||
            !Number.isSafeInteger(value.view_id) ||
            value.view_id <= 0
        ) {
            return null;
        }
        return Object.freeze({ ...common, model: value.model, view_id: value.view_id });
    }
    if (value.kind === "odoo_menu") {
        if (
            !exactKeys(value, ["kind", "label", "description", "model", "action_id", "menu_id"]) ||
            !MODEL_RE.test(value.model) ||
            !Number.isSafeInteger(value.action_id) ||
            value.action_id <= 0 ||
            !Number.isSafeInteger(value.menu_id) ||
            value.menu_id <= 0
        ) {
            return null;
        }
        return Object.freeze({
            ...common,
            model: value.model,
            action_id: value.action_id,
            menu_id: value.menu_id,
        });
    }
    if (
        !exactKeys(value, [
            "kind",
            "label",
            "description",
            "model",
            "action_id",
            "setting_field",
        ]) ||
        value.model !== "res.config.settings" ||
        !Number.isSafeInteger(value.action_id) ||
        value.action_id <= 0 ||
        typeof value.setting_field !== "string" ||
        !FIELD_RE.test(value.setting_field)
    ) {
        return null;
    }
    return Object.freeze({
        ...common,
        model: value.model,
        action_id: value.action_id,
        setting_field: value.setting_field,
    });
}

export function normalizeHostNavigationReferences(value, maximum = 12) {
    if (!Array.isArray(value) || value.length > maximum) {
        return null;
    }
    const result = [];
    for (const raw of value) {
        const reference = normalizeHostNavigationReference(raw);
        if (!reference) {
            return null;
        }
        result.push(reference);
    }
    return Object.freeze(result);
}

function normalizeFields(value) {
    if (!Array.isArray(value) || value.length > 3) {
        return null;
    }
    const fields = [];
    for (const item of value) {
        if (
            !item ||
            typeof item !== "object" ||
            typeof item.name !== "string" ||
            typeof item.label !== "string" ||
            !Object.hasOwn(item, "value")
        ) {
            return null;
        }
        fields.push({ name: item.name, label: item.label, value: item.value });
    }
    return fields;
}

function normalizeNavigation(value) {
    if (!value || typeof value !== "object") {
        return null;
    }
    if (value.mode === "record") {
        return exactKeys(value, ["mode", "model", "record_id"]) &&
            MODEL_RE.test(value.model) &&
            Number.isSafeInteger(value.record_id) &&
            value.record_id > 0
            ? Object.freeze({ ...value })
            : null;
    }
    if (value.mode === "model") {
        return exactKeys(value, ["mode", "model"]) && MODEL_RE.test(value.model)
            ? Object.freeze({ ...value })
            : null;
    }
    if (value.mode === "action") {
        return exactKeys(value, ["mode", "action_id"]) &&
            Number.isSafeInteger(value.action_id) &&
            value.action_id > 0
            ? Object.freeze({ ...value })
            : null;
    }
    if (value.mode === "view") {
        return exactKeys(value, ["mode", "model", "view_id", "view_type"]) &&
            MODEL_RE.test(value.model) &&
            Number.isSafeInteger(value.view_id) &&
            value.view_id > 0 &&
            VIEW_TYPES.has(value.view_type)
            ? Object.freeze({ ...value })
            : null;
    }
    return null;
}

function normalizeReference(value) {
    if (!value || typeof value !== "object" || !validLabel(value.label, 160)) {
        return null;
    }
    const navigation = normalizeNavigation(value.navigation);
    if (!navigation || !validLabel(value.description, 240)) {
        return null;
    }
    if (value.kind === "odoo_record") {
        if (
            !exactKeys(value, [
                "fields",
                "kind",
                "label",
                "model",
                "model_label",
                "navigation",
                "record_id",
                "description",
            ]) ||
            !MODEL_RE.test(value.model) ||
            !Number.isSafeInteger(value.record_id) ||
            value.record_id <= 0 ||
            typeof value.model_label !== "string" ||
            navigation.mode !== "record"
        ) {
            return null;
        }
        const fields = normalizeFields(value.fields);
        if (fields === null) {
            return null;
        }
        return Object.freeze({ ...value, navigation, fields: Object.freeze(fields) });
    }
    if (value.kind === "odoo_model") {
        if (
            !exactKeys(value, ["kind", "label", "model", "description", "navigation"]) ||
            !MODEL_RE.test(value.model) ||
            navigation.mode !== "model"
        ) {
            return null;
        }
        return Object.freeze({ ...value, navigation });
    }
    const expected = {
        odoo_action: ["kind", "action_id", "model", "label", "description", "navigation"],
        odoo_view: ["kind", "view_id", "model", "label", "description", "navigation"],
        odoo_menu: [
            "kind",
            "action_id",
            "menu_id",
            "model",
            "label",
            "description",
            "navigation",
        ],
        odoo_setting: [
            "kind",
            "action_id",
            "setting_field",
            "model",
            "label",
            "description",
            "navigation",
        ],
    }[value.kind];
    if (!expected || !exactKeys(value, expected) || !MODEL_RE.test(value.model)) {
        return null;
    }
    if (value.kind === "odoo_view") {
        if (!Number.isSafeInteger(value.view_id) || value.view_id <= 0 || navigation.mode !== "view") {
            return null;
        }
    } else if (
        !Number.isSafeInteger(value.action_id) ||
        value.action_id <= 0 ||
        navigation.mode !== "action"
    ) {
        return null;
    }
    if (
        value.kind === "odoo_menu" &&
        (!Number.isSafeInteger(value.menu_id) || value.menu_id <= 0)
    ) {
        return null;
    }
    if (
        value.kind === "odoo_setting" &&
        (typeof value.setting_field !== "string" || !FIELD_RE.test(value.setting_field))
    ) {
        return null;
    }
    return Object.freeze({ ...value, navigation });
}

export function normalizeReferenceResponse(response) {
    if (
        response?.ok !== true ||
        !Array.isArray(response.references) ||
        response.references.length < 1 ||
        response.references.length > MAX_REFERENCES
    ) {
        return null;
    }
    const result = [];
    for (const row of response.references) {
        if (row?.ok === false && row.error?.code === "reference_unavailable") {
            result.push(null);
            continue;
        }
        if (row?.ok !== true) {
            return null;
        }
        const reference = normalizeReference(row.reference);
        if (!reference) {
            return null;
        }
        result.push(reference);
    }
    return Object.freeze(result);
}

export function publicReferenceRequest(reference) {
    if (reference?.kind === "odoo_record") {
        return { kind: "odoo_record", model: reference.model, record_id: reference.record_id };
    }
    if (reference?.kind === "odoo_model") {
        return { kind: "odoo_model", model: reference.model };
    }
    if (reference?.kind === "odoo_action") {
        return { kind: "odoo_action", action_id: reference.action_id };
    }
    if (reference?.kind === "odoo_view") {
        return { kind: "odoo_view", view_id: reference.view_id };
    }
    if (reference?.kind === "odoo_menu") {
        return { kind: "odoo_menu", menu_id: reference.menu_id };
    }
    if (reference?.kind === "odoo_setting") {
        return {
            kind: "odoo_setting",
            action_id: reference.action_id,
            setting_field: reference.setting_field,
        };
    }
    return null;
}

export async function resolvePublicReferences(references, { rpcCall = rpc } = {}) {
    if (
        !Array.isArray(references) ||
        !references.length ||
        references.length > MAX_REFERENCES ||
        typeof rpcCall !== "function"
    ) {
        return null;
    }
    const request = references.map(publicReferenceRequest);
    if (request.some((item) => item === null)) {
        return null;
    }
    try {
        return normalizeReferenceResponse(
            await rpcCall("/odoo_ai/v1/public-references", { references: request })
        );
    } catch {
        return null;
    }
}

export async function openPublicReference(reference, { actionService, rpcCall = rpc } = {}) {
    if (!actionService || typeof actionService.doAction !== "function") {
        return false;
    }
    const resolved = await resolvePublicReferences([reference], { rpcCall });
    const target = resolved?.[0];
    if (!target) {
        return false;
    }
    let action;
    if (target.navigation.mode === "action") {
        action = target.navigation.action_id;
    } else if (target.navigation.mode === "view") {
        action = {
            type: "ir.actions.act_window",
            res_model: target.navigation.model,
            target: "current",
            views: [[target.navigation.view_id, target.navigation.view_type]],
        };
    } else if (target.navigation.mode === "record") {
        action = {
            type: "ir.actions.act_window",
            res_model: target.navigation.model,
            res_id: target.navigation.record_id,
            target: "current",
            views: [[false, "form"]],
        };
    } else if (target.navigation.mode === "model") {
        action = {
            type: "ir.actions.act_window",
            res_model: target.navigation.model,
            target: "current",
            views: [
                [false, "list"],
                [false, "form"],
            ],
        };
    } else {
        return false;
    }
    try {
        await actionService.doAction(action);
    } catch {
        return false;
    }
    return true;
}

export function referenceDisclosure(
    references,
    { pageSize = 5, visibleCount = null, maximumRows = MAX_RENDERED_REFERENCES } = {}
) {
    const total = Array.isArray(references) ? references.length : 0;
    const hardLimit =
        Number.isSafeInteger(maximumRows) && maximumRows >= 1 && maximumRows <= MAX_RENDERED_REFERENCES
            ? maximumRows
            : MAX_RENDERED_REFERENCES;
    const source = Array.isArray(references) ? references.slice(0, hardLimit) : [];
    const size = Number.isSafeInteger(pageSize) && pageSize >= 1 && pageSize <= 20 ? pageSize : 5;
    const requested = Number.isSafeInteger(visibleCount) && visibleCount > 0 ? visibleCount : size;
    const count = Math.min(source.length, requested);
    const blocked = total > hardLimit;
    return Object.freeze({
        visible: Object.freeze(source.slice(0, count)),
        visible_count: count,
        total_count: total,
        remaining_count: Math.max(0, total - count),
        next_count: Math.min(size, Math.max(0, source.length - count)),
        can_show_more: count < source.length,
        can_show_remaining: !blocked && count < total,
        remaining_blocked: blocked,
        maximum_rows: hardLimit,
    });
}
