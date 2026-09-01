from __future__ import annotations

from copy import deepcopy

import pytest

from .catalog import (
    EXPECTED_SMOKE_IDS,
    CatalogError,
    load_catalog,
    select_scenarios,
    validate_catalog,
)


def test_v1_catalog_is_complete_and_frozen() -> None:
    payload = load_catalog()

    assert len(payload["scenarios"]) == 54
    assert tuple(payload["smoke_ids"]) == EXPECTED_SMOKE_IDS


def test_selectors_compose_without_changing_catalog_order() -> None:
    smoke = select_scenarios(suite="smoke")
    catalan_actions = select_scenarios(suite="full", language="ca", persona="business_user")

    assert [row["id"] for row in smoke] == list(EXPECTED_SMOKE_IDS)
    assert catalan_actions
    assert all(row["language"] == "ca" for row in catalan_actions)
    assert all(row["persona"] == "business_user" for row in catalan_actions)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value["scenarios"].pop(), "catalog_scenario_count_invalid"),
        (lambda value: value["scenarios"][1].update(id="PB-GEN-001"), "catalog_duplicate_id"),
        (lambda value: value["scenarios"][0].update(planning_mode="auto"), "scenario_planning_mode_invalid"),
    ],
)
def test_catalog_rejects_contract_drift(mutation, code: str) -> None:
    payload = deepcopy(load_catalog())
    mutation(payload)

    with pytest.raises(CatalogError, match=code):
        validate_catalog(payload)
