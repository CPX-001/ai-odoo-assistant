import { expect, test } from "@odoo/hoot";
import { failureMessage } from "@odoo_ai_assistant/components/assistant_panel/assistant_failure_messages";

for (const code of [
    "access_denied",
    "agent_budget_exceeded",
    "engine_timeout",
    "engine_unavailable",
    "invalid_context",
    "invalid_response",
    "service_unavailable",
]) {
    test(`failure ${code} is presented as an actionable assistant explanation`, () => {
        const message = failureMessage(code);

        expect(message).toInclude("Diagnóstico:");
        expect(message).toInclude("Motivo:");
        expect(message).toInclude("Solución:");
        expect(message).not.toInclude(code);
    });
}

test("context failures explicitly avoid screen-based authorization advice", () => {
    expect(failureMessage("invalid_context")).toInclude(
        "No necesitas abrir una pantalla concreta"
    );
});
