from odoo_ai.adapters.chat_routing import _ROUTING_INSTRUCTIONS
from odoo_ai.adapters.query_tools import (
    ODOO_AGGREGATE_RECORDS,
    ODOO_QUERY_RECORDS,
    query_tool_specs,
)


def test_router_preserves_broad_scope_instead_of_inventing_ownership() -> None:
    assert "Never narrow a broad request" in _ROUTING_INSTRUCTIONS
    assert "owned by, assigned to" in _ROUTING_INSTRUCTIONS
    assert "downstream Odoo tools enforce" in _ROUTING_INSTRUCTIONS


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
