import { expect, test } from "@odoo/hoot";
import { patchTranslations } from "@web/../tests/web_test_helpers";
import { failedActionMessage } from "@odoo_ai_assistant/components/assistant_panel/assistant_action_feedback";

function failedPlan(errorCode) {
    return {
        steps: [
            {
                receipt: {
                    error_code: errorCode,
                },
            },
        ],
    };
}

test("permission failure is explained without internal terminology", () => {
    patchTranslations();
    const message = failedActionMessage(failedPlan("access_denied"));

    expect(message).toInclude("permisos");
    expect(message).toInclude("no lo doy por completado");
    expect(message).not.toInclude("access_denied");
    expect(message).not.toInclude("ACL");
});

test("stale data invites the assistant-safe retry path", () => {
    patchTranslations();
    const message = failedActionMessage(failedPlan("stale_precondition"));

    expect(message).toInclude("cambió");
    expect(message).toInclude("volver a leer");
    expect(message).not.toInclude("stale_precondition");
});

test("unverified execution warns before repeating the write", () => {
    patchTranslations();
    const message = failedActionMessage(failedPlan("verification_unavailable"));

    expect(message).toInclude("verificar");
    expect(message).toInclude("antes de repetir");
    expect(message).not.toInclude("verification_unavailable");
});

test("unknown execution failure does not invent a root cause", () => {
    patchTranslations();
    const message = failedActionMessage(failedPlan("some_internal_failure"));

    expect(message).toInclude("No voy a inventar");
    expect(message).toInclude("estado actual");
    expect(message).not.toInclude("some_internal_failure");
});
