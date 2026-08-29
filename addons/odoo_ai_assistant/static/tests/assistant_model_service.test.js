/** @odoo-module **/

import { expect, test } from "@odoo/hoot";
import {
    compactModelLabel,
    groupModelOptions,
    normalizeModelPreferences,
} from "@odoo_ai_assistant/services/assistant_model_service";

const EFFORTS = Object.freeze([
    { effort: "none", description: "Fast" },
    { effort: "medium", description: "Balanced" },
    { effort: "max", description: "Deep" },
]);

function model(modelId, variant, { alias = false, isDefault = false } = {}) {
    return {
        model: modelId,
        display_name: modelId,
        description: "",
        family: "gpt-5.6",
        variant,
        family_alias: alias,
        supported_reasoning_efforts: EFFORTS,
        default_reasoning_effort: "medium",
        is_default: isDefault,
    };
}

test("compact model label keeps the useful version and family", () => {
    expect(compactModelLabel("GPT-5.6 Codex")).toBe("5.6 Codex");
    expect(compactModelLabel("gpt-5.6-sol-medium")).toBe("5.6 Sol medium");
    expect(compactModelLabel(null)).toBe("");
});

test("model preferences accept a bounded per-user catalog", () => {
    const result = normalizeModelPreferences({
        ok: true,
        models: [
            { model: "gpt-5-codex", display_name: "GPT-5 Codex", is_default: true },
            { model: "gpt-fast", display_name: "GPT Fast", is_default: false },
        ],
        default_model: "gpt-5-codex",
        selected_model: "gpt-fast",
        can_manage_settings: true,
    });

    expect(result.selectedModel).toBe("gpt-fast");
    expect(result.defaultModel).toBe("gpt-5-codex");
    expect(result.selectedReasoningEffort).toBe(null);
    expect(result.models).toHaveLength(2);
    expect(result.canManageSettings).toBe(true);
});

test("model response preserves provider reasoning metadata", () => {
    const normalized = normalizeModelPreferences({
        ok: true,
        models: [model("gpt-5.6-sol", "sol", { isDefault: true })],
        default_model: "gpt-5.6-sol",
        selected_model: "gpt-5.6-sol",
        selected_reasoning_effort: "max",
        can_manage_settings: false,
    });

    expect(normalized).not.toBe(null);
    expect(normalized.selectedReasoningEffort).toBe("max");
    expect(normalized.models[0].default_reasoning_effort).toBe("medium");
    expect(normalized.models[0].supported_reasoning_efforts).toHaveLength(3);
});

test("GPT named variants render as one family and family alias does not duplicate Sol", () => {
    const normalized = normalizeModelPreferences({
        ok: true,
        models: [
            model("gpt-5.6", "sol", { alias: true, isDefault: true }),
            model("gpt-5.6-sol", "sol"),
            model("gpt-5.6-terra", "terra"),
            model("gpt-5.6-luna", "luna"),
        ],
        default_model: "gpt-5.6",
        selected_model: null,
        selected_reasoning_effort: null,
        can_manage_settings: false,
    });
    const groups = groupModelOptions(normalized.models);

    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("GPT-5.6");
    expect(groups[0].hasVariants).toBe(true);
    expect(groups[0].models.map((item) => item.variant)).toEqual(["sol", "terra", "luna"]);
    expect(groups[0].models[0].model).toBe("gpt-5.6-sol");
});

test("model preferences reject duplicate, malformed or inconsistent metadata", () => {
    expect(
        normalizeModelPreferences({
            ok: true,
            models: [
                { model: "same", display_name: "One", is_default: false },
                { model: "same", display_name: "Two", is_default: false },
            ],
            default_model: null,
            selected_model: null,
            can_manage_settings: false,
        })
    ).toBe(null);

    expect(
        normalizeModelPreferences({
            ok: true,
            models: [{ model: "../bad", display_name: "Bad", is_default: false }],
            default_model: null,
            selected_model: null,
            can_manage_settings: false,
        })
    ).toBe(null);

    const malformed = model("gpt-5.6-sol", "sol");
    malformed.supported_reasoning_efforts = [
        { effort: "high", description: "one" },
        { effort: "high", description: "duplicate" },
    ];
    expect(
        normalizeModelPreferences({
            ok: true,
            models: [malformed],
            default_model: "gpt-5.6-sol",
            selected_model: null,
            selected_reasoning_effort: null,
            can_manage_settings: false,
        })
    ).toBe(null);
});
