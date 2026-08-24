import asyncio
from datetime import UTC, datetime

from odoo_ai.adapters import user_model_engine
from odoo_ai.adapters.codex_runtime import CodexRuntimeSettings
from odoo_ai.contracts import (
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    InstanceProfileSummary,
    ScreenContext,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
    Workflow,
)

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _context(model: str) -> ContextPack:
    screen = ScreenContext(model="sale.order", view_type="list", captured_at=NOW)
    return ContextPack(
        request=UserRequest(message="List quotations"),
        screen=screen,
        user=UserExecutionContext(
            uid=7,
            company_id=1,
            allowed_company_ids=[1],
            reasoning_model=model,
        ),
        workflow_hint=Workflow.QUERY,
        instance=InstanceProfileSummary(instance_id="test"),
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=0, max_evidence_items=0),
    )


def test_user_model_replaces_only_the_inner_turn_settings(monkeypatch) -> None:
    captured = {}

    class FakeInnerEngine:
        def __init__(self, settings, *, limits, tool_executor_factory):
            captured["model"] = settings.model
            captured["limits"] = limits
            captured["factory"] = tool_executor_factory
            self.last_metadata = None

        async def run_turn(self, context, tools, output_schema):
            del context, tools, output_schema
            return AnswerEnvelope(
                answer_markdown="ok",
                workflow=Workflow.QUERY,
                confidence="high",
                evidence_refs=[],
                limitations=[],
                proposed_action=None,
            )

    monkeypatch.setattr(
        user_model_engine,
        "BaseCodexAppServerEngine",
        FakeInnerEngine,
    )
    settings = CodexRuntimeSettings(executable=None, model="global-model")
    engine = user_model_engine.UserSelectableCodexAppServerEngine(settings)

    answer = asyncio.run(
        engine.run_turn(
            _context("gpt-5-codex"),
            [],
            AnswerEnvelope.model_json_schema(),
        )
    )

    assert answer.answer_markdown == "ok"
    assert captured["model"] == "gpt-5-codex"
    assert settings.model == "global-model"
