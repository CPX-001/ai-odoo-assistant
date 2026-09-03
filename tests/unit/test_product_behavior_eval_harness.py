from tests.product_behavior.v1.harness import (
    Observation,
    derive_stage_durations,
    diagnostic_provider_timings,
    grade_observation,
)
from tests.product_behavior.v1.runner import run_product_behavior
from tests.product_behavior.v1.scenarios import (
    LANGUAGES,
    PERSONAS,
    SCENARIOS,
    SMOKE_IDS,
    select_scenarios,
    trials_for,
)
from tests.product_behavior.v1.selectors import select_product_behavior


def test_catalog_matches_frozen_v1_shape():
    assert len(SCENARIOS) == 56
    assert len({scenario.id for scenario in SCENARIOS}) == 56
    assert len(SMOKE_IDS) == 15
    assert {scenario.id for scenario in select_scenarios("smoke")} == set(SMOKE_IDS)
    assert select_scenarios("full") == SCENARIOS
    assert trials_for("smoke") == 1
    assert trials_for("full") == 3
    assert all(scenario.language in LANGUAGES for scenario in SCENARIOS)
    assert all(scenario.persona in PERSONAS for scenario in SCENARIOS)


def test_selectors_can_filter_without_changing_frozen_suites():
    selected = select_product_behavior(
        suite="full",
        family="read",
        language="es",
        persona="limited_user",
    )
    assert {scenario.id for scenario in selected} == {"PB-READ-010"}
    explicit = select_product_behavior(
        suite="smoke",
        scenario_ids=("PB-GEN-001", "PB-UX-001"),
    )
    assert [scenario.id for scenario in explicit] == ["PB-GEN-001", "PB-UX-001"]


def test_hard_safety_failure_is_never_averaged_away_by_quality_score():
    scenario = next(item for item in SCENARIOS if item.id == "PB-GEN-001")
    observation = Observation(
        scenario_id=scenario.id,
        trial=1,
        audit_complete=True,
        signals={requirement: True for requirement in scenario.hard},
        quality_dimensions={"answer_clarity": 1.0, "task_correctness": 1.0},
        unauthorized_write=True,
    )
    grade = grade_observation(scenario, observation)
    assert grade.quality_score_0_100 == 100.0
    assert grade.hard_pass is False
    assert "unauthorized_write" in grade.hard_failures


def test_missing_scenario_signal_fails_closed():
    scenario = next(item for item in SCENARIOS if item.id == "PB-READ-001")
    signals = {requirement: True for requirement in scenario.hard}
    signals.pop("live_grounding")
    grade = grade_observation(
        scenario,
        Observation(
            scenario_id=scenario.id,
            trial=1,
            audit_complete=True,
            signals=signals,
        ),
    )
    assert grade.hard_pass is False
    assert "requirement:live_grounding" in grade.hard_failures


def test_safe_event_timing_pairs_by_activity_id():
    events = (
        {
            "type": "tool.started",
            "payload": {"activity_id": "activity:v1:0123456789abcdef0123456789abcdef"},
            "occurred_at": "2026-08-31T10:00:00.000000Z",
        },
        {
            "type": "tool.completed",
            "payload": {"activity_id": "activity:v1:0123456789abcdef0123456789abcdef"},
            "occurred_at": "2026-08-31T10:00:00.125000Z",
        },
    )
    durations = derive_stage_durations(events)
    assert len(durations) == 1
    assert durations[0].stage == "tool"
    assert durations[0].duration_ms == 125.0
    assert durations[0].outcome == "completed"


def test_provider_timing_extractor_uses_only_sanitized_duration():
    events = (
        {
            "type": "diagnostic.provider.decision",
            "payload": {"duration_ms": 432.125, "outcome": "completed"},
        },
        {
            "type": "diagnostic.provider.decision",
            "payload": {"duration_ms": 10.0, "outcome": "failed"},
        },
    )
    assert diagnostic_provider_timings(events) == (432.125, 10.0)


class _PassingExecutor:
    def __init__(self):
        self.prepared = []
        self.cleaned = []

    def prepare(self, scenario, *, trial):
        self.prepared.append((scenario.id, trial))

    def observe(self, scenario, *, trial):
        return Observation(
            scenario_id=scenario.id,
            trial=trial,
            audit_complete=True,
            signals={requirement: True for requirement in scenario.hard},
            timings_ms={"final": 120.0},
        )

    def cleanup(self, scenario, *, trial):
        self.cleaned.append((scenario.id, trial))


def test_runner_applies_smoke_trial_count_and_always_cleans_prepared_fixtures():
    executor = _PassingExecutor()
    report = run_product_behavior(executor, suite="smoke")
    assert report.hard_pass is True
    assert len(report.grades) == 15
    assert executor.cleaned == executor.prepared
    payload = report.evidence_payload()
    assert payload["hard_pass"] is True
    assert payload["scenario_trials"] == 15
    assert all("prompt" not in row for row in payload["grades"])
