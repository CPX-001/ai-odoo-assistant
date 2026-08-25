/** @odoo-module **/

import { expect, test } from "@odoo/hoot";
import {
    compactModelLabel,
    normalizeModelPreferences,
} from "@odoo_ai_assistant/services/assistant_model_service";

test("compact model label keeps the useful version and family", () => {
    expect(compactModelLabel("GPT-5.6 Codex")).toBe("5.6 Codex");
    expect(compactModelLabel("gpt-5.6-sol-medium")).toBe("5.6 Sol medium");
    expect(compactModelLabel(null)).toBe("Predeterminado");
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
    expect(result.models).toHaveLength(2);
    expect(result.canManageSettings).toBe(true);
});

test("model preferences reject duplicate or malformed model ids", () => {
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
});
