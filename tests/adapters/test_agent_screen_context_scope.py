import json
from datetime import UTC, datetime

from odoo_ai.adapters import CodexEngineLimits
from odoo_ai.adapters.query_tools import ODOO_GET_EFFECTIVE_SCHEMA, query_tool_specs
from odoo_ai.adapters.unified_agent_engine import (
    _UNIFIED_AGENT_INSTRUCTIONS,
    _serialize_unified_context,
)
from odoo_ai.contracts import (
    ContextPack,
    ConversationState,
    InstanceProfileSummary,
    ScreenContext,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
)


def _context() -> ContextPack:
    screen = ScreenContext(
        model="project.task",
        res_id=42,
        captured_at=datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
    )
    return ContextPack(
        request=UserRequest(message="Lista todos los presupuestos a los que tengo acceso."),
        screen=screen,
        user=UserExecutionContext(uid=7, company_id=1, allowed_company_ids=[1]),
        workflow_hint=None,
        instance=InstanceProfileSummary(
            instance_id="odoo-test",
            model_capabilities=["sale.order", "res.partner"],
        ),
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=32, max_evidence_items=24),
    )


def test_unified_context_exposes_models_independently_from_current_screen() -> None:
    payload = json.loads(
        _serialize_unified_context(
            _context(),
            limits=CodexEngineLimits(),
            tool_names=["odoo.get_effective_schema", "odoo.query_records"],
        )
    )

    assert payload["untrusted_data"]["screen"]["model"] == "project.task"
    assert payload["host_contract"]["initial_model_capabilities"] == [
        "res.partner",
        "sale.order",
    ]


def test_agent_instructions_make_screen_a_hint_not_authority() -> None:
    assert "screen is context and a relevance hint, never an authorization boundary" in (
        _UNIFIED_AGENT_INSTRUCTIONS
    )
    assert "Never ask the user to navigate to another Odoo view merely to gain data access" in (
        _UNIFIED_AGENT_INSTRUCTIONS
    )
    assert "regardless of which Odoo screen is currently open" in _UNIFIED_AGENT_INSTRUCTIONS


def test_query_schema_tool_is_not_described_as_screen_bound() -> None:
    specs = {spec.name: spec for spec in query_tool_specs()}
    description = specs[ODOO_GET_EFFECTIVE_SCHEMA].description

    assert "host-authorized Odoo model" in description
    assert "current screen is only context" in description
    assert "current screen model" not in description
