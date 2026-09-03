import { expect, test } from "@odoo/hoot";
import { normalizeChatResponse } from "@odoo_ai_assistant/services/assistant_panel_service";
import {
    normalizeLiveTaskPlan,
    selectVisibleTaskPlan,
} from "@odoo_ai_assistant/services/zzzzzz_phase6_task_plan_live_service";

function terminalResponse(taskPlan) {
    return {
        ok: true,
        workflow: "AGENT",
        turn_id: "12345678-1234-5678-9234-567812345678",
        conversation_id: "22345678-1234-5678-9234-567812345678",
        answer: "Resultado final",
        confidence: "high",
        limitations: [],
        citations: [],
        plan: {
            plan_id: "32345678-1234-5678-9234-567812345678",
            state: "completed",
            risk: "low",
            metadata: {},
            policy: {
                confirmation_mode: "risk_based",
                max_auto_risk: "moderate",
                allow_synthetic_data: true,
                constrained_by: [],
            },
            goal: "Responder",
            assumptions: [],
            steps: [],
            requires_confirmation: false,
            expires_at: null,
        },
        task_plan: taskPlan,
    };
}

function taskPlan(revision, title, revisionKind = revision === 1 ? "initial" : "progress") {
    return {
        goal: "Resolver la petición",
        revision,
        revision_kind: revisionKind,
        revision_summary:
            revisionKind === "replan" ? "Nueva evidencia cambió el plan." : "",
        steps: [
            {
                step_id: "inspect",
                title,
                state: revision > 1 ? "completed" : "in_progress",
                depends_on: [],
            },
            {
                step_id: "answer",
                title: "Responder",
                state: revision > 1 ? "completed" : "pending",
                depends_on: ["inspect"],
            },
        ],
    };
}

test("terminal response accepts the current TaskPlan revision contract", () => {
    const parsed = normalizeChatResponse(terminalResponse(taskPlan(2, "Verificar", "replan")));

    expect(parsed.errorCode).toBe(null);
    expect(parsed.result.task_plan.revision).toBe(2);
    expect(parsed.result.task_plan.revision_kind).toBe("replan");
    expect(parsed.result.task_plan.revision_summary).toBe("Nueva evidencia cambió el plan.");
});

test("visible TaskPlan never lets a stale live revision hide a newer final revision", () => {
    const live = taskPlan(2, "Plan live anterior");
    const final = taskPlan(3, "Plan final más reciente", "replan");

    const visible = selectVisibleTaskPlan(live, final);

    expect(visible.revision).toBe(3);
    expect(visible.steps[0].title).toBe("Plan final más reciente");
});

test("Direct mode suppresses live TaskPlan while preserving host-validated final history", () => {
    const live = taskPlan(2, "Plan interno en curso");
    const final = taskPlan(3, "Plan interno final", "replan");

    expect(selectVisibleTaskPlan(live, null, false)).toBe(null);
    expect(selectVisibleTaskPlan(live, final, false)?.revision).toBe(3);
    expect(selectVisibleTaskPlan(live, final, true)?.revision).toBe(3);
});

test("final TaskPlan wins an equal-revision race and legacy payloads remain readable", () => {
    const live = taskPlan(2, "Live");
    const final = taskPlan(2, "Final");
    expect(selectVisibleTaskPlan(live, final).steps[0].title).toBe("Final");

    const legacy = {
        goal: "Compatibilidad",
        revision: 1,
        steps: [
            {
                step_id: "legacy",
                title: "Paso heredado",
                state: "in_progress",
                depends_on: [],
            },
        ],
    };
    const normalized = normalizeLiveTaskPlan(legacy);
    expect(normalized.revision_kind).toBe("initial");
    expect(normalized.revision_summary).toBe("");
});

test("completed one-step plans stay hidden while blocked work remains informative", () => {
    const trivial = taskPlan(1, "Responder al saludo");
    trivial.steps = [
        { step_id: "reply", title: "Saludar", state: "completed", depends_on: [] },
    ];
    expect(selectVisibleTaskPlan(null, trivial)).toBe(null);

    const blocked = taskPlan(1, "Comprobar acceso");
    blocked.steps = [
        { step_id: "access", title: "Comprobar acceso", state: "blocked", depends_on: [] },
    ];
    expect(selectVisibleTaskPlan(null, blocked)?.steps[0].state).toBe("blocked");
});
