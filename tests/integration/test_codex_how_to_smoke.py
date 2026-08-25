"""Opt-in real structured HOW_TO turn with synthetic checked evidence."""

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

NAVIGATION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SCHEMA_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
DOCUMENT_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


@pytest.mark.skipif(
    not os.environ.get("ODOO_AI_RUN_CODEX_HOW_TO_SMOKE"),
    reason="real authenticated Codex HOW_TO smoke is opt-in",
)
def test_real_codex_returns_structured_how_to_with_checked_refs() -> None:
    now = datetime.now(UTC)
    screen = ScreenContext(
        model="sale.order", menu_id=11, view_type="form", captured_at=now
    )
    evidence = [
        Evidence(
            evidence_id=NAVIGATION_ID,
            kind=EvidenceKind.METADATA,
            status=EvidenceStatus.CHECKED,
            title="Visible menu",
            summary="Sales > Orders is visible.",
            payload={
                "menu_id": 11,
                "path": ["Sales", "Orders"],
                "target_model": "sale.order",
            },
            pointer={"provider": "odoo_navigation", "menu_id": 11},
            observed_at=now,
            sensitivity=EvidenceSensitivity.TECHNICAL,
        ),
        Evidence(
            evidence_id=SCHEMA_ID,
            kind=EvidenceKind.METADATA,
            status=EvidenceStatus.CHECKED,
            title="Effective schema",
            summary="The state field is visible.",
            payload={"model": "sale.order", "fields": {"state": {"type": "selection"}}},
            pointer={"provider": "effective_schema", "model": "sale.order"},
            observed_at=now,
            sensitivity=EvidenceSensitivity.TECHNICAL,
        ),
        Evidence(
            evidence_id=DOCUMENT_ID,
            kind=EvidenceKind.DOCUMENT,
            status=EvidenceStatus.CHECKED,
            title="Sales guide",
            summary="A quotation can be confirmed from the Orders form.",
            payload={"lines": [{"number": 10, "text": "Confirm the quotation."}]},
            pointer={"provider_id": "synthetic", "document_id": "sales.md"},
            observed_at=now,
            sensitivity=EvidenceSensitivity.NORMAL,
            fingerprint="sha256:" + "d" * 64,
        ),
    ]
    context = ContextPack(
        request=UserRequest(
            message=(
                "Using only the supplied checked evidence, explain how to open Sales "
                "> Orders and inspect the state field. Return workflow HOW_TO, no "
                "action, and cite all relevant evidence ids."
            )
        ),
        screen=screen,
        user=UserExecutionContext(uid=17, company_id=3, allowed_company_ids=[3]),
        workflow_hint=Workflow.HOW_TO,
        instance=InstanceProfileSummary(instance_id="synthetic-how-to"),
        live_evidence=evidence,
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=0, max_evidence_items=3),
    )

    answer = asyncio.run(
        CodexAppServerEngine(CodexRuntimeSettings.from_env()).run_turn(
            context, [], AnswerEnvelope.model_json_schema()
        )
    )

    assert answer.workflow is Workflow.HOW_TO
    assert answer.proposed_action is None
    assert set(answer.evidence_refs).issubset(
        {NAVIGATION_ID, SCHEMA_ID, DOCUMENT_ID}
    )
