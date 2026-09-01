/** @odoo-module **/

import { expect, test } from "@odoo/hoot";
import {
    AUTO_REASONING_EFFORT,
    compactModelLabel,
    groupModelOptions,
    normalizeModelPreferences,
    pickerReasoningEfforts,
    supportsAutoReasoning,
} from "@odoo_ai_assistant/services/assistant_model_service";

const EFFORTS = Object.freeze([
    { effort: "none", description: "Fastest" },
    { effort: "low", description: "Fast" },
    { effort: "medium", description: "Balanced" },
    { effort: "high", description: "Deep" },
    { effort: "max", description: "Maximum" },
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
    expect(normalized.models[0].supported_reasoning_efforts).toHaveLength(5);
});

test("reasoning picker exposes normal levels through high and Auto separately", () => {
    expect(pickerReasoningEfforts(EFFORTS).map((item) => item.effort)).toEqual([
        "none",
        "low",
        "medium",
        "high",
    ]);
    expect(supportsAutoReasoning({ supported_reasoning_efforts: EFFORTS })).toBe(true);
    expect(pickerReasoningEfforts(null)).toEqual([]);
});

test("Auto is a host mode and is accepted only when low medium high are available", () => {
    const normalized = normalizeModelPreferences({
        ok: true,
        models: [model("gpt-5.6-sol", "sol", { isDefault: true })],
        default_model: "gpt-5.6-sol",
        selected_model: null,
        selected_reasoning_effort: AUTO_REASONING_EFFORT,
        can_manage_settings: false,
    });
    expect(normalized).not.toBe(null);
    expect(normalized.selectedReasoningEffort).toBe("auto");

    const limited = model("gpt-limited", null, { isDefault: true });
    limited.supported_reasoning_efforts = [
        { effort: "low", description: "" },
        { effort: "medium", description: "" },
    ];
    limited.default_reasoning_effort = "medium";
    expect(
        normalizeModelPreferences({
            ok: true,
            models: [limited],
            default_model: "gpt-limited",
            selected_model: null,
            selected_reasoning_effort: "auto",
            can_manage_settings: false,
        })
    ).toBe(null);
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

    const missingSupported = model("gpt-5.6-sol", "sol");
    missingSupported.supported_reasoning_efforts = [];
    expect(
        normalizeModelPreferences({
            ok: true,
            models: [missingSupported],
            default_model: "gpt-5.6-sol",
            selected_model: null,
            selected_reasoning_effort: null,
            can_manage_settings: false,
        })
    ).toBe(null);

    expect(
        normalizeModelPreferences({
            ok: true,
            models: [model("gpt-5.6-sol", "sol")],
            default_model: "gpt-5.6-sol",
            selected_model: null,
            selected_reasoning_effort: "minimal",
            can_manage_settings: false,
        })
    ).toBe(null);
});
