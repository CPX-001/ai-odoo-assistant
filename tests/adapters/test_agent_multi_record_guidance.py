from odoo_ai.adapters.batch_agent_tools import batch_tool_spec
from odoo_ai.adapters.unified_agent_engine import _UNIFIED_AGENT_INSTRUCTIONS


def test_multi_record_mutations_prefer_one_batch_preview() -> None:
    instructions = _UNIFIED_AGENT_INSTRUCTIONS

    assert "odoo.preview_batch_mutation" in instructions
    assert "If two or more records" in instructions
    assert "prefer one\nbatch preview" in instructions
    assert "do not query each record separately" in instructions
    assert "For batch delete, omit schema_id" in instructions


def test_multi_record_scope_relies_on_odoo_permissions_not_owner_filters() -> None:
    instructions = _UNIFIED_AGENT_INSTRUCTIONS

    assert "ACLs and record rules" in instructions
    assert "Never add owner, salesperson, assigned-user, user_id, create_uid" in instructions
    assert "all/every/todos/todas" in instructions
    assert "truncated=true" in instructions


def test_batch_delete_description_explains_canonical_item_shape() -> None:
    description = batch_tool_spec().description

    assert "For delete, omit schema_id" in description
    assert "operation='delete'" in description
    assert "record:<id>" in description
    assert "record_id" in description
    assert "source_ref values must be unique" in description
