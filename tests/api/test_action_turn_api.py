import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response

from odoo_ai.api import create_app
from odoo_ai.application import ActionTurnError
from odoo_ai.contracts import (
    ActionPreviewChange,
    ActionProposalHandle,
    ActionTarget,
    ActionTurnRequest,
    ActionTurnResponse,
    ActionValue,
    ActionValueKind,
    AnswerConfidence,
)
from odoo_ai.security import SHARED_SECRET_HEADER

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
TURN_ID = UUID("c0000000-0000-4000-8000-00000000000c")
PROPOSAL_ID = UUID("d0000000-0000-4000-8000-00000000000d")
EVIDENCE_ID = UUID("e0000000-0000-4000-8000-00000000000e")
SECRET = "action-turn-secret-" + "s" * 48
TOKEN = "p1." + "x" * 256


class StubActionService:
    def __init__(self, failure: ActionTurnError | None = None) -> None:
        self.failure = failure
        self.requests: list[ActionTurnRequest] = []

    async def run(self, request: ActionTurnRequest) -> ActionTurnResponse:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return ActionTurnResponse(
            turn_id=request.turn_id,
            answer_markdown="Preview lista.",
            confidence=AnswerConfidence.HIGH,
            evidence_refs=(EVIDENCE_ID,),
            proposal=ActionProposalHandle(
                proposal_id=PROPOSAL_ID,
                turn_id=request.turn_id,
                payload_fingerprint="action-payload:v1:sha256:" + "a" * 64,
                precondition_fingerprint="action-precondition:v1:sha256:" + "b" * 64,
                target=ActionTarget(model="res.partner", record_id=42),
                changes=(
                    ActionPreviewChange(
                        field="name",
                        label="Name",
                        before=ActionValue(kind=ActionValueKind.TEXT, value="OLD"),
                        after=ActionValue(kind=ActionValueKind.TEXT, value="NEW"),
                    ),
                ),
                warnings=("Approval required",),
                expires_at=NOW + timedelta(minutes=2),
                evidence_id=EVIDENCE_ID,
            ),
            completed_at=NOW,
        )


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "shared-secret"
    path.write_text(SECRET, encoding="utf-8")
    path.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(path))


def _payload(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "turn_id": str(TURN_ID),
        "message": "Cambia el nombre",
        "screen": {
            "view_type": "form",
            "model": "res.partner",
            "res_id": 42,
            "selected_ids": [],
            "captured_at": NOW.isoformat(),
        },
        "user": {
            "uid": 17,
            "company_id": 3,
            "allowed_company_ids": [3],
            "lang": "es_ES",
        },
        "delegation_token": TOKEN,
        "gateway": {"database": "fixture-db"},
    }
    result.update(updates)
    return result


async def _post(app: object, payload: dict[str, object], *, auth: bool = True) -> Response:
    transport = ASGITransport(app=app)
    headers = {SHARED_SECRET_HEADER: SECRET} if auth else {}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/v1/turns/action", json=payload, headers=headers)


def test_action_turn_is_authenticated_and_returns_no_preview_authority() -> None:
    service = StubActionService()
    app = create_app(action_service=service)  # type: ignore[arg-type]

    response = asyncio.run(_post(app, _payload()))

    assert response.status_code == 200
    assert response.json()["workflow"] == "ACTION"
    assert response.json()["proposal"]["proposal_id"] == str(PROPOSAL_ID)
    assert "approval_id" not in response.text
    assert "authority" not in response.text
    assert TOKEN not in response.text
    assert asyncio.run(_post(app, _payload(), auth=False)).status_code == 401


def test_action_turn_validation_and_failure_are_sanitized() -> None:
    service = StubActionService()
    app = create_app(action_service=service)  # type: ignore[arg-type]
    invalid = _payload(extra="forbidden")

    response = asyncio.run(_post(app, invalid))

    assert response.status_code == 422
    assert service.requests == []
    failing = create_app(
        action_service=StubActionService(ActionTurnError("action_rejected", 422))  # type: ignore[arg-type]
    )
    failure = asyncio.run(_post(failing, _payload()))
    assert failure.status_code == 422
    assert failure.json() == {"error": {"code": "action_rejected"}, "ok": False}
