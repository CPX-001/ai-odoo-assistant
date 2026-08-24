from odoo_ai.adapters.codex_engine import _AGENT_TOOL_INSTRUCTIONS
from odoo_ai.adapters.query_tools import (
    ODOO_AGGREGATE_RECORDS,
    ODOO_QUERY_RECORDS,
    query_tool_specs,
)


def test_agent_uses_runtime_models_without_claiming_authority() -> None:
    assert "odoo.search_models" in _AGENT_TOOL_INSTRUCTIONS
    assert "custom, OCA, or third-party module" in _AGENT_TOOL_INSTRUCTIONS
    assert "cannot authorize" in _AGENT_TOOL_INSTRUCTIONS


def test_query_tools_delegate_visibility_to_native_odoo_permissions() -> None:
    specs = {spec.name: spec for spec in query_tool_specs()}
    records = specs[ODOO_QUERY_RECORDS].description
    aggregate = specs[ODOO_AGGREGATE_RECORDS].description

    assert "authenticated Odoo user" in records
    assert "Odoo ACLs, record rules, field access" in records
    assert "Never add owner" in records
    assert "user_id" in records
    assert "create_uid" in records

    assert "authenticated Odoo user" in aggregate
    assert "Odoo itself applies ACLs, record rules" in aggregate
    assert "Never narrow by owner" in aggregate
