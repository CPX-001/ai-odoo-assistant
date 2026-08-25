"""Opt-in real structured-output smoke for Codex App Server."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from odoo_ai.adapters import CodexAppServerEngine, CodexRuntimeSettings
from odoo_ai.contracts import (
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    InstanceProfileSummary,
    ScreenContext,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
    Workflow,
)

EVIDENCE_ID = UUID("12345678-1234-5678-1234-567812345678")


@pytest.mark.skipif(
    not os.environ.get("ODOO_AI_RUN_CODEX_ENGINE_SMOKE"),
    reason="real authenticated Codex engine smoke is opt-in",
)
def test_real_codex_structured_output_with_synthetic_evidence() -> None:
    screen = ScreenContext(
        model="sale.order",
        res_id=56,
        captured_at=datetime(2026, 8, 22, 10, 30, tzinfo=UTC),
    )
    context = ContextPack(
        request=UserRequest(
            message="Explain the state using only the supplied evidence."
        ),
        screen=screen,
        user=UserExecutionContext(uid=7, company_id=1),
        workflow_hint=Workflow.EXPLAIN,
        instance=InstanceProfileSummary(instance_id="synthetic-smoke"),
        live_evidence=[
            Evidence(
                evidence_id=EVIDENCE_ID,
                kind=EvidenceKind.RECORD,
                status=EvidenceStatus.CHECKED,
                title="Synthetic quotation",
                summary="The synthetic quotation is in the sale state.",
                payload={"state": "sale"},
                sensitivity=EvidenceSensitivity.NORMAL,
            )
        ],
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=0, max_evidence_items=1),
    )
    engine = CodexAppServerEngine(CodexRuntimeSettings.from_env())

    answer = asyncio.run(
        engine.run_turn(context, [], AnswerEnvelope.model_json_schema())
    )

    assert answer.workflow is Workflow.EXPLAIN
    assert answer.proposed_action is None
    assert all(reference == EVIDENCE_ID for reference in answer.evidence_refs)
    assert engine.last_metadata is not None
    assert engine.last_metadata.status == "ok"
