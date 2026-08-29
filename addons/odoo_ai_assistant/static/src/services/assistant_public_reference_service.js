/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

const MODEL_RE = /^[A-Za-z_][A-Za-z0-9_.]{0,127}$/;
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

function normalizeReference(value) {
    if (!value || typeof value !== "object") {
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
            ]) ||
            !MODEL_RE.test(value.model) ||
            !Number.isSafeInteger(value.record_id) ||
            value.record_id <= 0 ||
            typeof value.label !== "string" ||
            typeof value.model_label !== "string" ||
            value.navigation?.view_type !== "form"
        ) {
            return null;
        }
        const fields = normalizeFields(value.fields);
        if (fields === null) {
            return null;
        }
        return Object.freeze({ ...value, fields: Object.freeze(fields) });
    }
    if (value.kind === "odoo_model") {
        if (
            !exactKeys(value, ["kind", "label", "model", "navigation"]) ||
            !MODEL_RE.test(value.model) ||
            typeof value.label !== "string" ||
            value.navigation?.view_type !== "list"
        ) {
            return null;
        }
        return Object.freeze({ ...value });
    }
    return null;
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

export async function resolvePublicReferences(references, { rpcCall = rpc } = {}) {
    if (
        !Array.isArray(references) ||
        !references.length ||
        references.length > MAX_REFERENCES ||
        typeof rpcCall !== "function"
    ) {
        return null;
    }
    const request = references.map((reference) => {
        if (reference?.kind === "odoo_record") {
            return {
                kind: "odoo_record",
                model: reference.model,
                record_id: reference.record_id,
            };
        }
        if (reference?.kind === "odoo_model") {
            return { kind: "odoo_model", model: reference.model };
        }
        return null;
    });
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

export async function openPublicReference(
    reference,
    { actionService, rpcCall = rpc } = {}
) {
    if (!actionService || typeof actionService.doAction !== "function") {
        return false;
    }
    const resolved = await resolvePublicReferences([reference], { rpcCall });
    const target = resolved?.[0];
    if (!target) {
        return false;
    }
    const action = {
        type: "ir.actions.act_window",
        res_model: target.model,
        target: "current",
    };
    if (target.kind === "odoo_record") {
        action.res_id = target.record_id;
        action.views = [[false, "form"]];
    } else {
        action.views = [
            [false, "list"],
            [false, "form"],
        ];
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
