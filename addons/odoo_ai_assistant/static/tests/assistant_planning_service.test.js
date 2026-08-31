import { expect, test } from "@odoo/hoot";
import {
    normalizePlanningModeResponse,
    planningModeAfterSubmit,
    PLANNING_MODES,
} from "@odoo_ai_assistant/services/assistant_planning_service";
import { normalizeLiveTaskPlan } from "@odoo_ai_assistant/services/zzzzzz_phase6_task_plan_live_service";


test("planning mode response exposes direct and explicit plan only", () => {
    expect(PLANNING_MODES).toEqual(["adaptive", "deliberate"]);
    expect(normalizePlanningModeResponse({ ok: true, mode: "adaptive" })).toBe("adaptive");
    expect(normalizePlanningModeResponse({ ok: true, mode: "deliberate" })).toBe("deliberate");
    expect(normalizePlanningModeResponse({ ok: true, mode: "auto" })).toBe(null);
    expect(normalizePlanningModeResponse({ ok: true, mode: "unbounded" })).toBe(null);
});


test("Plan is consumed only after a successful submitted turn", () => {
    expect(planningModeAfterSubmit("deliberate", true)).toBe("adaptive");
    expect(planningModeAfterSubmit("deliberate", false)).toBe("deliberate");
    expect(planningModeAfterSubmit("adaptive", true)).toBe("adaptive");
    expect(planningModeAfterSubmit("auto", true)).toBe("adaptive");
});


test("live TaskPlan accepts bounded public replan metadata", () => {
    const plan = normalizeLiveTaskPlan({
        goal: "Resolver la incidencia",
        revision: 2,
        revision_kind: "replan",
        revision_summary: "La consulta descartó la primera hipótesis.",
        steps: [
            {
                step_id: "inspect",
                title: "Comprobar la nueva hipótesis",
                state: "in_progress",
                depends_on: [],
            },
        ],
    });

    expect(plan.revision).toBe(2);
    expect(plan.revision_kind).toBe("replan");
    expect(plan.revision_summary).toBe("La consulta descartó la primera hipótesis.");
    expect(Object.hasOwn(plan.steps[0], "capability")).toBe(false);
});


test("live TaskPlan rejects authority fields and unexplained replans", () => {
    const unexplained = {
        goal: "Resolver",
        revision: 2,
        revision_kind: "replan",
        revision_summary: "",
        steps: [
            {
                step_id: "one",
                title: "Continuar",
                state: "in_progress",
                depends_on: [],
            },
        ],
    };
    expect(normalizeLiveTaskPlan(unexplained)).toBe(undefined);

    unexplained.revision_summary = "Nueva evidencia";
    unexplained.steps[0].capability = "odoo.record.patch";
    expect(normalizeLiveTaskPlan(unexplained)).toBe(undefined);
});