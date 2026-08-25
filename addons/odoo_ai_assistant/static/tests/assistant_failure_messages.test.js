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
    test(`failure ${code} is presented as a plain assistant fallback`, () => {
        const message = failureMessage(code);

        expect(message.length).toBeGreaterThan(20);
        expect(message).not.toInclude("Diagnóstico:");
        expect(message).not.toInclude("Motivo:");
        expect(message).not.toInclude("Solución:");
        expect(message).not.toInclude("ACL");
        expect(message).not.toInclude("App Server");
        expect(message).not.toInclude(code);
    });
}

test("context failures explicitly avoid screen-based authorization advice", () => {
    expect(failureMessage("invalid_context")).toInclude(
        "No necesitas abrir una pantalla concreta"
    );
});

test("unknown failures admit when the cause is not known", () => {
    expect(failureMessage("some_new_internal_failure")).toInclude(
        "no voy a inventarla"
    );
});
