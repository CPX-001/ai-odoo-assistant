import { expect, test } from "@odoo/hoot";
import {
    normalizeServerPreferences,
    validPreferencePatch,
} from "@odoo_ai_assistant/services/assistant_activity_preferences_service";

function response(overrides = {}) {
    return {
        ok: true,
        detail_level: "normal",
        transient_threshold_ms: 1200,
        batch_page_size: 5,
        expanded_line_count: 5,
        show_technical_names: false,
        show_step_durations: false,
        reasoning_summary: "concise",
        limits: {
            max_rendered_activity_items: 100,
            max_rendered_batch_rows: 100,
            max_reasoning_summary_chars: 2000,
        },
        ...overrides,
    };
}

test("activity preference response is normalized and bounded", () => {
    const normalized = normalizeServerPreferences(response({ detail_level: "detailed" }));
    expect(normalized.detail_level).toBe("detailed");
    expect(normalized.batch_page_size).toBe(5);
    expect(normalized.expanded_line_count).toBe(5);
    expect(normalized.limits.max_reasoning_summary_chars).toBe(2000);
});

test("malformed activity preference response fails closed", () => {
    expect(normalizeServerPreferences(response({ detail_level: "private" }))).toBe(null);
    expect(normalizeServerPreferences(response({ batch_page_size: 200 }))).toBe(null);
    expect(normalizeServerPreferences(response({ expanded_line_count: 21 }))).toBe(null);
    expect(normalizeServerPreferences(response({ show_technical_names: "yes" }))).toBe(null);
});

test("activity preference mutation accepts only the closed presentation contract", () => {
    expect(validPreferencePatch({ detail_level: "compact" })).toBe(true);
    expect(validPreferencePatch({ reasoning_summary: "off", show_technical_names: true })).toBe(true);
    expect(validPreferencePatch({ expanded_line_count: 8 })).toBe(true);
    expect(validPreferencePatch({ detail_level: "raw" })).toBe(false);
    expect(validPreferencePatch({ private_reasoning: true })).toBe(false);
    expect(validPreferencePatch({ expanded_line_count: 0 })).toBe(false);
    expect(validPreferencePatch({})).toBe(false);
});
