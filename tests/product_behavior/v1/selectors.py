"""Stable selectors for Product Behavior Evals v1."""

from __future__ import annotations

from collections.abc import Iterable

from .scenarios import LANGUAGES, PERSONAS, Scenario, select_scenarios


def select_product_behavior(
    *,
    suite: str,
    scenario_ids: Iterable[str] | None = None,
    family: str | None = None,
    language: str | None = None,
    persona: str | None = None,
) -> tuple[Scenario, ...]:
    if language is not None and language not in LANGUAGES:
        raise ValueError("product_behavior_language_invalid")
    if persona is not None and persona not in PERSONAS:
        raise ValueError("product_behavior_persona_invalid")

    selected = select_scenarios(suite)
    requested_ids = set(scenario_ids or ())
    if requested_ids:
        known = {scenario.id for scenario in selected}
        if not requested_ids.issubset(known):
            raise ValueError("product_behavior_scenario_invalid")
        selected = tuple(scenario for scenario in selected if scenario.id in requested_ids)
    if family is not None:
        selected = tuple(scenario for scenario in selected if scenario.family == family)
    if language is not None:
        selected = tuple(scenario for scenario in selected if scenario.language == language)
    if persona is not None:
        selected = tuple(scenario for scenario in selected if scenario.persona == persona)
    return selected
