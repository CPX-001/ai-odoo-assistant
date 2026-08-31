"""Reusable orchestration for Product Behavior Evals v1.

Environment-specific executors own disposable Odoo fixtures and browser/provider driving.
The generic runner owns selection, trial counts, deterministic grading and guaranteed cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .harness import Observation, RunGrade, grade_observation
from .scenarios import Scenario, trials_for
from .selectors import select_product_behavior


class ScenarioExecutor(Protocol):
    def prepare(self, scenario: Scenario, *, trial: int) -> None: ...

    def observe(self, scenario: Scenario, *, trial: int) -> Observation: ...

    def cleanup(self, scenario: Scenario, *, trial: int) -> None: ...


@dataclass(frozen=True, slots=True)
class SuiteReport:
    suite: str
    grades: tuple[RunGrade, ...]

    @property
    def hard_pass(self) -> bool:
        return bool(self.grades) and all(grade.hard_pass for grade in self.grades)

    @property
    def hard_failures(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "scenario_id": grade.scenario_id,
                "trial": grade.trial,
                "failures": list(grade.hard_failures),
            }
            for grade in self.grades
            if not grade.hard_pass
        )

    def evidence_payload(self) -> dict[str, object]:
        """Sanitized report payload: no prompt/tool args/results/private reasoning."""

        return {
            "suite": self.suite,
            "scenario_trials": len(self.grades),
            "hard_pass": self.hard_pass,
            "hard_failures": list(self.hard_failures),
            "grades": [
                {
                    "scenario_id": grade.scenario_id,
                    "trial": grade.trial,
                    "hard_pass": grade.hard_pass,
                    "hard_failures": list(grade.hard_failures),
                    "quality_score_0_100": grade.quality_score_0_100,
                    "metrics": dict(grade.metrics),
                }
                for grade in self.grades
            ],
        }


def run_product_behavior(
    executor: ScenarioExecutor,
    *,
    suite: str,
    scenario_ids: tuple[str, ...] | None = None,
    family: str | None = None,
    language: str | None = None,
    persona: str | None = None,
    trials: int | None = None,
) -> SuiteReport:
    scenarios = select_product_behavior(
        suite=suite,
        scenario_ids=scenario_ids,
        family=family,
        language=language,
        persona=persona,
    )
    if not scenarios:
        raise ValueError("product_behavior_selection_empty")
    trial_count = trials if trials is not None else trials_for(suite)
    if type(trial_count) is not int or not 1 <= trial_count <= 10:
        raise ValueError("product_behavior_trials_invalid")

    grades: list[RunGrade] = []
    for scenario in scenarios:
        for trial in range(1, trial_count + 1):
            prepared = False
            try:
                executor.prepare(scenario, trial=trial)
                prepared = True
                observation = executor.observe(scenario, trial=trial)
                grades.append(grade_observation(scenario, observation))
            finally:
                if prepared:
                    executor.cleanup(scenario, trial=trial)
    return SuiteReport(suite=suite, grades=tuple(grades))
