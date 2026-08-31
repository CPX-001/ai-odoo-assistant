import { expect, test } from "@odoo/hoot";
import { planningToggleTarget } from "@odoo_ai_assistant/components/assistant_planning/assistant_planning";


test("composer Plan action toggles between direct and deliberate", () => {
    expect(planningToggleTarget("adaptive")).toBe("deliberate");
    expect(planningToggleTarget("deliberate")).toBe("adaptive");
    expect(planningToggleTarget("unknown")).toBe("deliberate");
});
