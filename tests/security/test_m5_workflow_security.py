from pathlib import Path

from odoo_ai.adapters import (
    knowledge_tool_specs,
    query_tool_specs,
    source_tool_specs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDON_ROOT = REPO_ROOT / "addons" / "odoo_ai_assistant"


def test_each_read_only_workflow_has_an_exact_disjoint_registry() -> None:
    registries = {
        "EXPLAIN": {spec.name for spec in source_tool_specs()},
        "QUERY": {spec.name for spec in query_tool_specs()},
        "HOW_TO": {spec.name for spec in knowledge_tool_specs()},
    }

    assert registries == {
        "EXPLAIN": {
            "source.find_model_extensions",
            "source.find_symbol",
            "source.read_excerpt",
        },
        "QUERY": {
            "odoo.aggregate_records",
            "odoo.get_effective_schema",
            "odoo.query_records",
        },
        "HOW_TO": {
            "knowledge.read_excerpt",
            "knowledge.search",
        },
    }
    assert all(
        left.isdisjoint(right)
        for index, left in enumerate(registries.values())
        for right in list(registries.values())[index + 1 :]
    )
    advertised = set().union(*registries.values())
    assert not any(
        forbidden in tool_name
        for tool_name in advertised
        for forbidden in ("action", "business", "commit", "create", "update", "write")
    )


def test_unified_browser_agent_is_text_only_and_has_no_authority_data() -> None:
    service = (
        ADDON_ROOT / "static" / "src" / "services" / "assistant_panel_service.js"
    ).read_text(encoding="utf-8")
    template = (
        ADDON_ROOT
        / "static"
        / "src"
        / "components"
        / "assistant_panel"
        / "assistant_panel.xml"
    ).read_text(encoding="utf-8")

    assert 'rpcCall("/odoo_ai/v1/chat"' in service
    assert 'new Set(["AGENT"])' in service
    for workflow in ("EXPLAIN", "QUERY", "HOW_TO", "ACTION"):
        assert f'"{workflow}"' not in service
    assert 'rpcCall("/odoo_ai/v1/agent-plan-decision", {' in service
    assert "plan_id: planId" in service
    assert "decision," in service
    assert "CHAT_WORKFLOWS" in service
    assert "t-esc" in template
    assert "t-raw" not in template
    assert "innerHTML" not in service
    assert "delegation" not in service.lower()
    assert "shared_secret" not in service.lower()
    assert "127.0.0.1" not in service
