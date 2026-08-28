import { expect, test } from "@odoo/hoot";
import { patchTranslations } from "@web/../tests/web_test_helpers";
import {
    AssistantFailureError,
    failureCanRetry,
    failureErrorFromStatus,
    failureFromError,
    normalizeFailureEnvelope,
} from "@odoo_ai_assistant/services/assistant_failure_contract";
import { failurePresentation } from "@odoo_ai_assistant/components/assistant_panel/assistant_failure_messages";

function failure(overrides = {}) {
    return {
        code: "codex_turn_failed",
        category: "provider_connection",
        stage: "provider",
        component: "codex",
        retryability: "safe",
        effect_state: "none",
        user_action: "retry",
        safe_summary: "Host generated summary",
        safe_details: { http_status: 503 },
        diagnostic_id: "diag-p24-00000001",
        provider_code: "responseStreamDisconnected",
        ...overrides,
    };
}

test("valid browser failure preserves the bounded machine contract", () => {
    const parsed = normalizeFailureEnvelope(failure(), "codex_turn_failed");
    expect(parsed.category).toBe("provider_connection");
    expect(parsed.retryability).toBe("safe");
    expect(parsed.effect_state).toBe("none");
    expect(parsed.user_action).toBe("retry");
    expect(parsed.diagnostic_id).toBe("diag-p24-00000001");
    expect(parsed.provider_code).toBe("responseStreamDisconnected");
});

test("tampered or mismatched failure fails closed and keeps only bounded legacy code", () => {
    expect(normalizeFailureEnvelope({ ...failure(), surprise: true })).toBe(null);
    expect(normalizeFailureEnvelope(failure(), "different_code")).toBe(null);
    const error = failureErrorFromStatus({
        state: "failed",
        error_code: "codex_turn_failed",
        failure: { ...failure(), safe_details: { authorization_token: "secret" } },
    });
    expect(error.message).toBe("codex_turn_failed");
    expect(error.failure).toBe(null);
});

test("safe retry requires explicit retryability, safe effect state and retry action", () => {
    expect(failureCanRetry(normalizeFailureEnvelope(failure()))).toBe(true);
    for (const mutation of [
        { retryability: "never" },
        { effect_state: "unknown" },
        { effect_state: "partial" },
        { user_action: "review" },
    ]) {
        expect(failureCanRetry(normalizeFailureEnvelope(failure(mutation)))).toBe(false);
    }
});

test("recovery_required is browser-authoritative even if a payload claims safe retry", () => {
    const error = failureErrorFromStatus({
        state: "recovery_required",
        error_code: "codex_turn_failed",
        failure: failure(),
    });
    expect(error.failure.effect_state).toBe("unknown");
    expect(error.failure.retryability).toBe("never");
    expect(error.failure.user_action).toBe("review");
    expect(failureCanRetry(error.failure)).toBe(false);

    const partial = failureErrorFromStatus({
        state: "recovery_required",
        error_code: "codex_turn_failed",
        failure: failure({ effect_state: "partial" }),
    });
    expect(partial.failure.effect_state).toBe("partial");
    expect(partial.failure.retryability).toBe("never");
    expect(partial.failure.user_action).toBe("review");
});

test("auth, ACL, timeout, tool failure and recovery produce distinct deterministic presentation", () => {
    patchTranslations();
    const cases = [
        [
            failure({
                category: "authentication",
                retryability: "after_change",
                user_action: "reconnect",
            }),
            "autenticación",
        ],
        [
            failure({
                code: "access_denied",
                category: "odoo_access",
                component: "odoo",
                retryability: "after_change",
                user_action: "request_access",
                provider_code: null,
            }),
            "permisos",
        ],
        [
            failure({
                code: "engine_timeout",
                category: "provider_connection",
                provider_code: null,
            }),
            "comunicación",
        ],
        [
            failure({
                code: "capability_execution_failed",
                category: "capability_execution",
                component: "capability",
                stage: "capability",
                retryability: "never",
                user_action: "review",
                provider_code: null,
            }),
            "herramienta",
        ],
        [
            failure({
                code: "worker_lost_after_write_barrier",
                category: "queue_worker",
                component: "queue",
                stage: "execution",
                retryability: "never",
                effect_state: "unknown",
                user_action: "review",
                provider_code: null,
            }),
            "no se puede confirmar",
        ],
    ];
    for (const [raw, text] of cases) {
        const view = failurePresentation(normalizeFailureEnvelope(raw), raw.code);
        expect(`${view.body} ${view.effect} ${view.next}`.toLowerCase()).toInclude(text);
    }
});

test("unknown stream errors retain a bounded real code instead of universal service_unavailable", () => {
    const parsed = failureFromError(new Error("connection_lost"));
    expect(parsed.code).toBe("connection_lost");
    expect(parsed.failure).toBe(null);
    const structured = failureFromError(
        new AssistantFailureError("codex_turn_failed", normalizeFailureEnvelope(failure()))
    );
    expect(structured.failure.category).toBe("provider_connection");
});

test("presentation never renders safe_details, provider code or raw summary", () => {
    patchTranslations();
    const raw = failure({
        safe_summary: "DO NOT DISPLAY RAW SUMMARY",
        safe_details: { http_status: 503, upstream_code: "bounded" },
        provider_code: "serverOverloaded",
    });
    const rendered = JSON.stringify(failurePresentation(normalizeFailureEnvelope(raw), raw.code));
    expect(rendered).not.toInclude("DO NOT DISPLAY RAW SUMMARY");
    expect(rendered).not.toInclude("serverOverloaded");
    expect(rendered).not.toInclude("http_status");
    expect(rendered).toInclude("diag-p24-00000001");
});
