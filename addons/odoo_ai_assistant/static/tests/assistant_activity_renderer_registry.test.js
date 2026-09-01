import { beforeEach, expect, test } from "@odoo/hoot";
import { patchTranslations } from "@web/../tests/web_test_helpers";
import {
    activityRendererRegistry,
    renderActivityLabel,
} from "@odoo_ai_assistant/services/assistant_activity_renderer_registry";

beforeEach(() => patchTranslations({}));

function item(semanticCode, headlineArgs) {
    return {
        semantic_code: semanticCode,
        headline_args: headlineArgs,
    };
}

test("query activity uses model, fields and filters instead of a generic tool label", () => {
    const label = renderActivityLabel(
        item("activity.query.records", {
            model_label: "Contacts",
            fields_label: "Email, Company",
            filter_label: "Company, Status",
        })
    );

    expect(label).toBe("Consulting Email, Company in Contacts, filtered by Company, Status");
});

test("aggregate activity explains metric and grouping", () => {
    const label = renderActivityLabel(
        item("activity.aggregate.records", {
            model_label: "Invoices",
            metric_operation: "sum",
            metric_label: "Total",
            metric_count: 1,
            group_label: "Customer",
        })
    );

    expect(label).toBe("Calculating total Total in Invoices, grouped by Customer");
});

test("model and navigation discovery render the actual semantic query", () => {
    expect(
        renderActivityLabel(item("activity.search.odoo", { query: "custom quality check" }))
    ).toBe('Finding Odoo models related to "custom quality check"');
    expect(
        renderActivityLabel(item("activity.navigation.resolve", { query: "custom quality check" }))
    ).toBe('Finding where to open "custom quality check" in Odoo');
});

test("third-party capabilities can provide safe text without a frontend patch", () => {
    expect(
        renderActivityLabel(
            item("activity.vendor.custom", {
                headline_text: "Inspecting custom compliance rules",
            })
        )
    ).toBe("Inspecting custom compliance rules");
});

test("third-party addons can register a localized renderer through the Odoo registry", () => {
    const code = "activity.test.registry_extension";
    activityRendererRegistry.add(code, (value) => `Custom: ${value.headline_args.object_label}`);
    try {
        expect(renderActivityLabel(item(code, { object_label: "Quality batch" }))).toBe(
            "Custom: Quality batch"
        );
    } finally {
        activityRendererRegistry.remove(code);
    }
});
