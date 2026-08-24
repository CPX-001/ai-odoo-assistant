import { expect, test } from "@odoo/hoot";
import {
    AUTONOMY_PROFILES,
    normalizeAutonomyResponse,
} from "@odoo_ai_assistant/services/assistant_autonomy_service";


test("autonomy response accepts the four supported profiles", () => {
    expect(AUTONOMY_PROFILES).toHaveLength(4);
    for (const profile of AUTONOMY_PROFILES) {
        expect(normalizeAutonomyResponse({ ok: true, profile })).toBe(profile);
    }
});


test("autonomy response rejects unknown or malformed profiles", () => {
    expect(normalizeAutonomyResponse({ ok: true, profile: "unrestricted-root" })).toBe(null);
    expect(normalizeAutonomyResponse({ ok: false, profile: "balanced" })).toBe(null);
    expect(normalizeAutonomyResponse({ ok: true })).toBe(null);
});
