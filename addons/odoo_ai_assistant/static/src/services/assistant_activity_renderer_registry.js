/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

/**
 * Odoo-native extension point for public Assistant activity labels.
 *
 * Capability projectors own trusted, bounded facts; renderers own localized presentation.
 * Third-party addons can register a renderer for their own headline_code without patching the
 * Assistant panel. Unknown codes keep the existing generic fallback in the panel component.
 */
export const activityRendererRegistry = registry.category(
    "odoo_ai_assistant.activity_renderers"
);

function text(value) {
    return typeof value === "string" && value.trim() ? value.trim() : "";
}

function queryRecordsLabel(item) {
    const args = item?.headline_args || {};
    const model = text(args.model_label) || _t("Odoo records");
    const fields = text(args.fields_label);
    const filter = text(args.filter_label);
    if (fields && filter) {
        return _t("Consulting %s in %s, filtered by %s", fields, model, filter);
    }
    if (fields) {
        return _t("Consulting %s in %s", fields, model);
    }
    if (filter) {
        return _t("Searching %s, filtered by %s", model, filter);
    }
    return _t("Consulting %s", model);
}

function aggregateBaseLabel(args) {
    const model = text(args.model_label) || _t("Odoo records");
    const metric = text(args.metric_label);
    const operation = text(args.metric_operation);
    const count = Number.isSafeInteger(args.metric_count) ? args.metric_count : null;
    if (operation === "count") {
        return _t("Counting %s", model);
    }
    if (operation === "sum" && metric) {
        return _t("Calculating total %s in %s", metric, model);
    }
    if (operation === "min" && metric) {
        return _t("Finding minimum %s in %s", metric, model);
    }
    if (operation === "max" && metric) {
        return _t("Finding maximum %s in %s", metric, model);
    }
    if (count && count > 1) {
        return _t("Calculating %s metrics for %s", count, model);
    }
    return _t("Aggregating %s", model);
}

function aggregateRecordsLabel(item) {
    const args = item?.headline_args || {};
    let label = aggregateBaseLabel(args);
    const group = text(args.group_label);
    const filter = text(args.filter_label);
    if (group && filter) {
        label = _t("%s, grouped by %s and filtered by %s", label, group, filter);
    } else if (group) {
        label = _t("%s, grouped by %s", label, group);
    } else if (filter) {
        label = _t("%s, filtered by %s", label, filter);
    }
    return label;
}

function searchModelsLabel(item) {
    const query = text(item?.headline_args?.query);
    return query
        ? _t('Finding Odoo models related to "%s"', query)
        : _t("Finding the relevant Odoo data");
}

function navigationLabel(item) {
    const query = text(item?.headline_args?.query);
    return query
        ? _t('Finding where to open "%s" in Odoo', query)
        : _t("Finding where to open it in Odoo");
}

activityRendererRegistry.add("activity.query.records", queryRecordsLabel);
activityRendererRegistry.add("activity.aggregate.records", aggregateRecordsLabel);
activityRendererRegistry.add("activity.search.odoo", searchModelsLabel);
activityRendererRegistry.add("activity.navigation.resolve", navigationLabel);

export function renderActivityLabel(item) {
    const explicit = text(item?.headline_args?.headline_text);
    if (explicit) {
        return explicit;
    }
    const code = item?.semantic_code;
    if (typeof code !== "string" || !activityRendererRegistry.contains(code)) {
        return "";
    }
    try {
        return text(activityRendererRegistry.get(code)(item));
    } catch {
        // Presentation extensions are never allowed to break the Assistant turn/UI.
        return "";
    }
}
