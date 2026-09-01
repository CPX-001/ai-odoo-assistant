"""Load and validate the versioned Product Behavior Evals v1 catalog."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name("scenarios_v1.json")
EXPECTED_SMOKE_IDS = (
    "PB-GEN-001",
    "PB-GEN-005",
    "PB-READ-001",
    "PB-READ-004",
    "PB-READ-010",
    "PB-HOW-002",
    "PB-ACT-001",
    "PB-ACT-007",
    "PB-ACT-008",
    "PB-ACT-009",
    "PB-UX-001",
    "PB-UX-002",
    "PB-UX-005",
    "PB-UX-006",
    "PB-PREF-004",
)
EXPECTED_LANGUAGES = {"es": 32, "ca": 11, "en": 11}
EXPECTED_CATEGORIES = {
    "general": 8,
    "read": 14,
    "how_to": 7,
    "action": 13,
    "ux": 8,
    "preference": 4,
}
PERSONAS = frozenset({"business_user", "limited_user", "admin_user"})


class CatalogError(ValueError):
    """The versioned product-behavior catalog violates its frozen contract."""


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_catalog(payload)
    return payload


def validate_catalog(payload: object) -> None:
    if not isinstance(payload, dict) or set(payload) != {"version", "smoke_ids", "scenarios"}:
        raise CatalogError("catalog_shape_invalid")
    if payload["version"] != 1:
        raise CatalogError("catalog_version_invalid")
    scenarios = payload["scenarios"]
    smoke_ids = payload["smoke_ids"]
    if not isinstance(scenarios, list) or len(scenarios) != 54:
        raise CatalogError("catalog_scenario_count_invalid")
    if not isinstance(smoke_ids, list) or tuple(smoke_ids) != EXPECTED_SMOKE_IDS:
        raise CatalogError("catalog_smoke_invalid")

    ids: list[str] = []
    languages: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise CatalogError("scenario_shape_invalid")
        required = {"id", "category", "language", "persona", "prompt", "setup", "hard", "bounds"}
        if not required.issubset(scenario):
            raise CatalogError("scenario_required_field_missing")
        scenario_id = scenario["id"]
        if not isinstance(scenario_id, str) or not scenario_id.startswith("PB-"):
            raise CatalogError("scenario_id_invalid")
        if scenario["persona"] not in PERSONAS:
            raise CatalogError("scenario_persona_invalid")
        if not isinstance(scenario["prompt"], str) or not scenario["prompt"].strip():
            raise CatalogError("scenario_prompt_invalid")
        if not isinstance(scenario["hard"], list) or not scenario["hard"]:
            raise CatalogError("scenario_hard_invalid")
        if not isinstance(scenario["bounds"], dict):
            raise CatalogError("scenario_bounds_invalid")
        if scenario.get("planning_mode", "adaptive") not in {"adaptive", "deliberate"}:
            raise CatalogError("scenario_planning_mode_invalid")
        ids.append(scenario_id)
        languages[scenario["language"]] += 1
        categories[scenario["category"]] += 1

    if len(ids) != len(set(ids)):
        raise CatalogError("catalog_duplicate_id")
    if set(smoke_ids) - set(ids):
        raise CatalogError("catalog_unknown_smoke_id")
    if dict(languages) != EXPECTED_LANGUAGES:
        raise CatalogError("catalog_language_matrix_invalid")
    if dict(categories) != EXPECTED_CATEGORIES:
        raise CatalogError("catalog_category_matrix_invalid")


def select_scenarios(
    *,
    suite: str,
    scenario_id: str | None = None,
    language: str | None = None,
    persona: str | None = None,
) -> list[dict[str, object]]:
    payload = load_catalog()
    scenarios = list(payload["scenarios"])
    if suite not in {"smoke", "full"}:
        raise CatalogError("suite_invalid")
    if suite == "smoke":
        allowed = set(payload["smoke_ids"])
        scenarios = [row for row in scenarios if row["id"] in allowed]
    if scenario_id:
        scenarios = [row for row in scenarios if row["id"] == scenario_id]
    if language:
        scenarios = [row for row in scenarios if row["language"] == language]
    if persona:
        scenarios = [row for row in scenarios if row["persona"] == persona]
    if not scenarios:
        raise CatalogError("selection_empty")
    return scenarios
